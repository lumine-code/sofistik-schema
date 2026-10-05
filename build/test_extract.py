"""Focused tests for the source catalogue parser."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("1_extract.py")
SPEC = importlib.util.spec_from_file_location("sofistik_extract", MODULE_PATH)
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class ExtractorTests(unittest.TestCase):
    def parse_schema(self, catalogue_text, module="TEST", language="en"):
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / f"{module.lower()}.err"
            catalogue.write_text(catalogue_text, encoding="utf-8")
            commands = extractor.parse_err_file(catalogue)["commands"]
            schema, _filled = extractor.build_language_schema(
                {module: commands}, language
            )
            extractor.resolve_enum_redirects(schema)
            return schema

    def test_preserves_native_prefixes_without_changing_normalized_kinds(self):
        schema = self.parse_schema(
            "0000TEST SOFiSTiK\n"
            "0000VERSION 202600\n"
            "-*0 TEST X FACT 'NO \"TYPE `NAME !FREE =EXPR\n"
        )
        slots = schema["TEST"]["TEST"]["forms"][0]["slots"]
        self.assertEqual(
            [(slot["name"], slot["nativePrefix"], slot["kind"]) for slot in slots],
            [
                ("X", "", "keyword"),
                ("FACT", "", "keyword"),
                ("NO", "'", "literal"),
                ("TYPE", '"', "enum"),
                ("NAME", "`", "comment"),
                ("FREE", "!", "keyword"),
                ("EXPR", "=", "keyword"),
            ],
        )

    def test_source_prefixes_distinguish_otherwise_identical_repeated_forms(self):
        schema = self.parse_schema(
            "0000TEST SOFiSTiK\n"
            "0000VERSION 202600\n"
            "-*0 ITEM VAL\n"
            "-*0 ITEM !VAL\n"
            "-*0 ITEM VAL\n"
        )
        forms = schema["TEST"]["ITEM"]["forms"]
        self.assertEqual(len(forms), 2)
        self.assertEqual(
            [form["slots"][0]["nativePrefix"] for form in forms], ["", "!"]
        )
        self.assertEqual([form["slots"][0]["kind"] for form in forms], ["keyword"] * 2)

    def test_native_prefixes_survive_localized_reference_hydration(self):
        with tempfile.TemporaryDirectory() as directory:
            basic = Path(directory) / "sofistik.err"
            basic.write_text(
                "0000SOFISTIK SOFiSTiK\n"
                "0000VERSION 202600\n"
                "-10 SEIT FIRS !MARG\n"
                "-20 PAGE FIRS !MARG\n",
                encoding="utf-8",
            )
            module = Path(directory) / "target.err"
            module.write_text(
                "0000TARGET SOFiSTiK\n"
                "0000VERSION 202600\n"
                "-10=SEIT\n"
                "-20=PAGE\n",
                encoding="utf-8",
            )
            commands = extractor.parse_all_err_files(directory)
            for language, name in (("en", "PAGE"), ("de", "SEIT")):
                schema, _filled = extractor.build_language_schema(commands, language)
                slots = schema["TARGET"][name]["forms"][0]["slots"]
                self.assertEqual([slot["nativePrefix"] for slot in slots], ["", "!"])
                self.assertEqual(schema["TARGET"][name], schema["BASIC"][name])
                self.assertIsNone(schema["TARGET"]["ECHO"]["forms"][0]["slots"][0]["nativePrefix"])

    def test_parses_a_complete_catalogue_through_localization(self):
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "dbin.err"
            catalogue.write_text(
                "0000DBIN SOFiSTiK\n"
                "0000VERSION 202600\n"
                "-*0=TEST NO \"TYPE\n"
                "-*12 A B\n",
                encoding="utf-8",
            )

            commands = extractor.parse_all_err_files(directory)
            self.assertIn("DBINFO", commands)

            for language in ("de", "en"):
                schema, _filled = extractor.build_language_schema(commands, language)
                slots = schema["DBINFO"]["TEST"]["forms"][0]["slots"]
                self.assertEqual([slot["name"] for slot in slots], ["NO", "TYPE"])
                self.assertEqual(slots[1]["enumValues"], ["A", "B"])

    def test_pairs_commands_from_separate_language_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "sofistik.err"
            catalogue.write_text(
                "0000SOFISTIK SOFiSTiK\n"
                "0000VERSION 202600\n"
                '-10 KOPF"XXXX\n'
                "-10 SEIT NRST\n"
                '-10 STEU"OPT VAL\n'
                "-10 ENDE\n"
                '-20 HEAD"XXXX\n'
                "-20 PAGE FIRS\n"
                '-20 CTRL"OPT VAL\n'
                "-20 END\n",
                encoding="utf-8",
            )

            parsed = extractor.parse_err_file(catalogue)
            self.assertEqual(
                [(command["de"], command["en"]) for command in parsed["commands"].values()],
                [
                    ("KOPF", "HEAD"),
                    ("SEIT", "PAGE"),
                    ("STEU", "CTRL"),
                    ("ENDE", "END"),
                ],
            )

            for language, expected in (
                ("de", {"KOPF", "SEIT", "STEU", "ENDE"}),
                ("en", {"HEAD", "PAGE", "CTRL", "END"}),
            ):
                schema, _filled = extractor.build_language_schema(
                    {"SOFISTIK": parsed["commands"]}, language
                )
                self.assertTrue(expected.issubset(schema["BASIC"]))

            english, _filled = extractor.build_language_schema(
                {"SOFISTIK": parsed["commands"]}, "en"
            )
            self.assertEqual(
                english["BASIC"]["CTRL"]["forms"][0]["slots"][0]["name"],
                "OPT",
            )

    def test_pairs_language_blocks_with_form_local_metadata(self):
        schema = self.parse_schema(
            "0000TEST SOFiSTiK\n"
            "0000VERSION 202600\n"
            '-10 ERST"TYP\n'
            '-10 ZWEI"MOD\n'
            '-20 FIRS"TYPE\n'
            "-*11 A\n"
            '-20 SECO"MODE\n'
            "-*11 B\n"
        )

        self.assertEqual(
            schema["TEST"]["FIRS"]["forms"][0]["slots"][0]["enumValues"],
            ["A"],
        )
        self.assertEqual(
            schema["TEST"]["SECO"]["forms"][0]["slots"][0]["enumValues"],
            ["B"],
        )

    def test_keeps_distinct_command_forms_and_scopes_their_enums(self):
        schema = self.parse_schema(
            "0000BDK SOFiSTiK\n"
            "0000VERSION 202600\n"
            '-10 EIGE"TYP  NEIG LFB\n'
            '-20 EIGE"TYPE NEIG LCB\n'
            "-111     BEUL NCRY NCRZ NCRT MCR\n"
            "-211     BUCK NCRY NCRZ NCRT MCR\n"
            '-10 EIGE STAB LF  "TYP  HORD\'DNR \'ENR\n'
            '-20 EIGE BEAM LC  "TYPE HORD\'DNO \'ENO\n',
            module="BDK",
        )

        forms = schema["BDK"]["EIGE"]["forms"]
        self.assertEqual(
            [[slot["name"] for slot in form["slots"]] for form in forms],
            [["TYPE", "NEIG", "LCB"], ["BEAM", "LC", "TYPE", "HORD", "DNO", "ENO"]],
        )
        self.assertEqual(
            forms[0]["slots"][0]["enumValues"],
            ["BUCK", "MCR", "NCRT", "NCRY", "NCRZ"],
        )
        self.assertEqual(forms[1]["slots"][2]["enumValues"], [])
        self.assertEqual(
            [[slot["position"] for slot in form["slots"]] for form in forms],
            [list(range(1, 4)), list(range(1, 7))],
        )

    def test_deduplicates_identical_complete_forms(self):
        schema = self.parse_schema(
            "0000TEXTILE SOFiSTiK\n"
            "0000VERSION 202200\n"
            "-10 CUTS I1 I2\n"
            "-20 CUTS I1 I2\n"
            "-10 CUTS I1 I2\n"
            "-20 CUTS I1 I2\n",
            module="TEXTILE",
        )

        forms = schema["TEXTILE"]["CUTS"]["forms"]
        self.assertEqual(len(forms), 1)
        self.assertEqual([slot["name"] for slot in forms[0]["slots"]], ["I1", "I2"])

    def test_distinguishes_references_from_argumentless_forms(self):
        parsed = extractor.parse_err_file
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "basic.err"
            catalogue.write_text(
                "0000SOFISTIK SOFiSTiK\n"
                "0000VERSION 202600\n"
                "-10=KOPF\n"
                "-20=HEAD\n"
                "-10 ENDE\n"
                "-20 END\n",
                encoding="utf-8",
            )
            commands = parsed(catalogue)["commands"]

        self.assertEqual(commands["KOPF"]["forms_de"], [])
        self.assertEqual(commands["KOPF"]["forms_en"], [])
        self.assertEqual(commands["ENDE"]["forms_de"], [{"slots": []}])
        self.assertEqual(commands["ENDE"]["forms_en"], [{"slots": []}])

    def test_extracts_numeric_and_punctuated_enum_values(self):
        values = extractor.extract_enum_values(
            "0 15 1045 2D 3D 2DSS 2A EC-0 SIG+ U-X A6.1 -EGX +X *SAR "
            ">FIX PT/P (-) NONE BEME'FILE"
        )

        self.assertEqual(
            values,
            [
                "0",
                "15",
                "1045",
                "2D",
                "3D",
                "2DSS",
                "2A",
                "EC-0",
                "SIG+",
                "U-X",
                "A6.1",
                "-EGX",
                "+X",
                "*SAR",
                ">FIX",
                "PT/P",
                "(-)",
                "NONE",
                "BEME",
                "FILE",
            ],
        )
        self.assertEqual(
            extractor.extract_enum_values("FULL YES NO obs. XXXX .... ... ..20"),
            ["FULL", "YES", "NO"],
        )
        self.assertEqual(
            extractor.extract_enum_values("FULL YES NO obs =OPT1"),
            ["FULL", "YES", "NO", "OBS", "=OPT1"],
        )
        self.assertEqual(extractor.extract_enum_values("F18 F19C"), ["F18", "F19C"])

    def test_resolves_letter_selectors_as_positions_twenty_through_thirty_five(self):
        slots = extractor.extract_param_slots(
            " ".join(f"P{position}" for position in range(1, 36))
        )

        self.assertEqual(extractor.target_slot(slots, "A")["name"], "P10")
        self.assertEqual(extractor.target_slot(slots, "K")["name"], "P20")
        self.assertEqual(extractor.target_slot(slots, "L")["name"], "P21")
        self.assertEqual(extractor.target_slot(slots, "Z")["name"], "P35")

    def test_assigns_high_position_enums_to_their_actual_slots(self):
        schema = self.parse_schema(
            "0000SOFILOAD SOFiSTiK\n"
            "0000VERSION 202600\n"
            '-*0 TRAI!TYPE\'P1 P2 P3 P4 P5 P6 P7 P8 P9 PFAC PFAV WIDT\'PHI '
            "'PHIS V FUGA XCON YEX \"DIR \"DIRT\n"
            "-*1K N R L B\n"
            "-*1L N R L B\n",
            module="SOFILOAD",
        )

        slots = schema["SOFILOAD"]["TRAI"]["forms"][0]["slots"]
        self.assertEqual(slots[19]["name"], "DIR")
        self.assertEqual(slots[20]["name"], "DIRT")
        self.assertEqual(slots[19]["enumValues"], ["B", "L", "N", "R"])
        self.assertEqual(slots[20]["enumValues"], ["B", "L", "N", "R"])
        self.assertTrue(all(not slot["enumValues"] for slot in slots[:19]))

    def test_recognizes_legacy_shared_data_type_rows(self):
        schema = self.parse_schema(
            "0000HYDRA SOFiSTiK\n"
            "0000VERSION 201800\n"
            "-10 LINK'NR   A    B    S    EPS\n"
            "-20 LINK'NO   A    B    S    EPS\n"
            "-*02          9999 9999 9999\n"
            "-*310158\n",
            module="HYDRA",
        )

        slots = schema["HYDRA"]["LINK"]["forms"][0]["slots"]
        self.assertEqual(
            [slot["dataTypeCode"] for slot in slots],
            [None, "9999", "9999", "9999", None],
        )
        self.assertTrue(all("0158" not in slot["enumValues"] for slot in slots))

    def test_pairs_adjacent_commands_with_legacy_delimiters(self):
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "bemess.err"
            catalogue.write_text(
                "0000BEMESS SOFiSTiK\n"
                "0000VERSION 202600\n"
                "-10 BEW`BEZ\n"
                "-20 REIN`TITL\n"
                "-10 SEIT=\n"
                "-20 PAGE=\n",
                encoding="utf-8",
            )

            commands = extractor.parse_err_file(catalogue)["commands"]
            self.assertEqual(
                (commands["BEW"]["de"], commands["BEW"]["en"]),
                ("BEW", "REIN"),
            )
            self.assertEqual(
                [
                    slot["name"]
                    for slot in commands["BEW"]["forms_de"][0]["slots"]
                ],
                ["BEZ"],
            )
            self.assertEqual(
                [
                    slot["name"]
                    for slot in commands["BEW"]["forms_en"][0]["slots"]
                ],
                ["TITL"],
            )
            self.assertEqual(
                (commands["SEIT"]["de"], commands["SEIT"]["en"]),
                ("SEIT", "PAGE"),
            )
            self.assertEqual(commands["SEIT"]["forms_de"], [])
            self.assertEqual(commands["SEIT"]["forms_en"], [])

    def test_clears_only_stale_intermediate_schema_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            stale_schema = output_dir / "sofistik.2026.en.schema.json"
            compact_data = output_dir / "sofistik.2026.en.json"
            unrelated_schema = output_dir / "notes.schema.json"
            for file in (stale_schema, compact_data, unrelated_schema):
                file.write_text("{}\n", encoding="utf-8")

            extractor.clear_extracted_schemas(output_dir)

            self.assertFalse(stale_schema.exists())
            self.assertTrue(compact_data.exists())
            self.assertTrue(unrelated_schema.exists())

    def test_rejects_a_missing_or_empty_release_source(self):
        with tempfile.TemporaryDirectory() as directory:
            build_dir = Path(directory)
            output_dir = build_dir / "extracted"
            with self.assertRaises(FileNotFoundError):
                extractor.process_version("2099", build_dir, output_dir)

            (build_dir / "2099").mkdir()
            with self.assertRaises(RuntimeError):
                extractor.process_version("2099", build_dir, output_dir)

    def test_keeps_localized_page_as_a_universal_basic_command(self):
        page = extractor.command_template("PAGE")
        page["de"] = "SEIT"
        page["forms_de"] = [{"slots": extractor.extract_param_slots("UNIE")}]
        page["forms_en"] = [{"slots": extractor.extract_param_slots("UNII")}]

        control = extractor.command_template("CTRL")
        control["forms_de"] = [{"slots": extractor.extract_param_slots("WARN")}]
        control["forms_en"] = [{"slots": extractor.extract_param_slots("WARN")}]

        page_reference = extractor.command_template("PAGE")
        page_reference["de"] = "SEIT"
        all_commands = {
            "SOFISTIK": {"PAGE": page, "CTRL": control},
            "ASE": {
                "PAGE": page_reference,
                "CTRL": extractor.command_template("CTRL"),
            },
        }

        for language, localized_page, localized_item in (
            ("en", "PAGE", "UNII"),
            ("de", "SEIT", "UNIE"),
        ):
            with self.subTest(language=language):
                schema, filled = extractor.build_language_schema(all_commands, language)

                self.assertEqual(
                    schema["ASE"][localized_page], schema["BASIC"][localized_page]
                )
                self.assertEqual(
                    schema["BASIC"][localized_page]["forms"][0]["slots"][0][
                        "name"
                    ],
                    localized_item,
                )
                self.assertIn(localized_page, filled)
                self.assertNotIn("CTRL", schema["BASIC"])

    def test_recovers_page_from_a_module_when_the_basic_source_is_missing(self):
        page = extractor.command_template("PAGE")
        page["de"] = "SEIT"
        page["forms_de"] = [{"slots": extractor.extract_param_slots("UNIE")}]
        page["forms_en"] = [{"slots": extractor.extract_param_slots("UNII")}]

        incomplete_basic_page = extractor.command_template("SEIT")
        all_commands = {
            "SOFISTIK": {"SEIT": incomplete_basic_page},
            "TENDON": {"PAGE": page},
            "ASE": {"PAGE": extractor.command_template("PAGE")},
        }

        schema, filled = extractor.build_language_schema(all_commands, "en")

        self.assertEqual(schema["BASIC"]["PAGE"], schema["TENDON"]["PAGE"])
        self.assertEqual(schema["ASE"]["PAGE"], schema["BASIC"]["PAGE"])
        self.assertEqual(
            schema["BASIC"]["PAGE"]["forms"][0]["slots"][0]["name"],
            "UNII",
        )
        self.assertIn("PAGE", filled)

    def test_preserves_prefixed_placeholders_and_repeated_names(self):
        slots = extractor.extract_param_slots('"XXXX GAMA"APAR"SUP "FAT APAR')

        self.assertEqual([slot["position"] for slot in slots], list(range(1, 7)))
        self.assertEqual(slots[0]["name"], None)
        self.assertEqual(slots[0]["kind"], "placeholder")
        self.assertEqual(
            [(slot["name"], slot["kind"]) for slot in slots[1:]],
            [
                ("GAMA", "keyword"),
                ("APAR", "enum"),
                ("SUP", "enum"),
                ("FAT", "enum"),
                ("APAR", "keyword"),
            ],
        )

    def test_preserves_directional_and_ratio_item_names(self):
        slots = extractor.extract_param_slots("P+ P- MY+ MY- A/U MUE-")

        self.assertEqual(
            [slot["name"] for slot in slots],
            ["P+", "P-", "MY+", "MY-", "A/U", "MUE-"],
        )
        prefixed = extractor.extract_param_slots('"P+ \'MY- !A/U')
        self.assertEqual(
            [(slot["name"], slot["kind"]) for slot in prefixed],
            [("P+", "enum"), ("MY-", "literal"), ("A/U", "keyword")],
        )

    def test_aligns_data_type_codes_by_source_column(self):
        slots = extractor.extract_param_slots('"OPT \'VAL  VAL2', start_column=8)
        line = "-*2" + " " * (slots[1]["_column"] - 3) + "9999"

        extractor.assign_data_types(slots, line)

        self.assertIsNone(slots[0]["dataTypeCode"])
        self.assertEqual(slots[1]["dataTypeCode"], "9999")
        self.assertIsNone(slots[2]["dataTypeCode"])

    def test_resolves_redirect_values_and_retains_provenance(self):
        schema = {
            "TEST": {
                "BASE": {
                    "forms": [
                        {
                            "slots": [
                                {
                                    "position": 1,
                                    "name": "TYPE",
                                    "kind": "enum",
                                    "dataTypeCode": None,
                                    "enumValues": ["A", "B"],
                                    "enumRedirect": None,
                                }
                            ]
                        }
                    ]
                },
                "USE": {
                    "forms": [
                        {
                            "slots": [
                                {
                                    "position": 1,
                                    "name": "MODE",
                                    "kind": "enum",
                                    "dataTypeCode": None,
                                    "enumValues": [],
                                    "enumRedirect": {
                                        "command": "BASE",
                                        "item": "TYPE",
                                    },
                                }
                            ]
                        }
                    ]
                },
            }
        }

        redirects, unresolved = extractor.resolve_enum_redirects(schema)

        self.assertEqual((redirects, unresolved), (1, 0))
        slot = schema["TEST"]["USE"]["forms"][0]["slots"][0]
        self.assertEqual(slot["enumValues"], ["A", "B"])
        self.assertEqual(
            slot["enumRedirect"],
            {"command": "BASE", "item": "TYPE"},
        )


if __name__ == "__main__":
    unittest.main()
