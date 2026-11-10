"""Tests for what the file tree shows left of a file's name: the kind and the visibility of the file's top-level type.

Run: python3 -m unittest discover -s tests
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"))
import _declarations as declarations  # noqa: E402


def top(path, text):
    return declarations.top_level(path, text)


class JavaTest(unittest.TestCase):
    def test_a_public_class(self):
        self.assertEqual(top("src/Desk.java", "package a;\n\npublic final class Desk {\n}\n"),
                         {"kind": "class", "visibility": "public"})

    def test_a_class_without_a_modifier_is_package_private(self):
        self.assertEqual(top("Desk.java", "class Desk {}"), {"kind": "class", "visibility": "package"})

    def test_every_kind_of_type(self):
        self.assertEqual(top("A.java", "public interface A {}")["kind"], "interface")
        self.assertEqual(top("A.java", "public record A(int x) {}")["kind"], "record")
        self.assertEqual(top("A.java", "public enum A { X }")["kind"], "enum")
        self.assertEqual(top("A.java", "public @interface A {}")["kind"], "annotation")
        self.assertEqual(top("A.java", "public abstract sealed class A permits B {}")["kind"], "class")

    def test_annotations_and_comments_before_the_type_are_skipped(self):
        text = ('/* interface Desk {} */\n// the enum Desk is gone\nimport a.B;\n\n@Service\n'
                '@RequiredArgsConstructor(x = "record Desk")\npublic class Desk {}\n')

        self.assertEqual(top("Desk.java", text), {"kind": "class", "visibility": "public"})

    def test_an_annotation_between_the_modifiers_keeps_the_visibility(self):
        self.assertEqual(top("Desk.java", "public @Deprecated(since = \"2\") final class Desk {}"),
                         {"kind": "class", "visibility": "public"})

    def test_the_type_named_after_the_file_wins_over_one_written_before_it(self):
        text = "class Helper {}\n\npublic interface Desk {}\n"

        self.assertEqual(top("Desk.java", text), {"kind": "interface", "visibility": "public"})

    def test_a_file_without_a_type_has_no_declaration(self):
        self.assertIsNone(top("package-info.java", "/** Docs. */\npackage a;\n"))


class GroovyAndKotlinTest(unittest.TestCase):
    def test_a_groovy_class_without_a_modifier_is_public(self):
        self.assertEqual(top("DeskSpec.groovy", "class DeskSpec extends Specification {}"),
                         {"kind": "class", "visibility": "public"})

    def test_a_groovy_trait_is_an_interface(self):
        self.assertEqual(top("Named.groovy", "trait Named {}")["kind"], "interface")

    def test_a_kotlin_class_without_a_modifier_is_public(self):
        self.assertEqual(top("Desk.kt", "package a\n\ndata class Desk(val id: Long)\n"),
                         {"kind": "class", "visibility": "public"})

    def test_kotlin_kinds(self):
        self.assertEqual(top("A.kt", "enum class A { X }")["kind"], "enum")
        self.assertEqual(top("A.kt", "annotation class A")["kind"], "annotation")
        self.assertEqual(top("A.kt", "sealed interface A")["kind"], "interface")
        self.assertEqual(top("A.kt", "fun interface A { fun x() }")["kind"], "interface")
        self.assertEqual(top("A.kt", "object A")["kind"], "class")

    def test_kotlin_private_and_internal(self):
        self.assertEqual(top("A.kt", "private class A")["visibility"], "private")
        self.assertEqual(top("A.kt", "internal class A")["visibility"], "package")


class TypeScriptTest(unittest.TestCase):
    def test_the_one_exported_type_has_no_visibility(self):
        self.assertEqual(top("desk.service.ts", "import x from 'y';\n\n@Injectable()\nexport class DeskService {}\n"),
                         {"kind": "class", "visibility": None})
        self.assertEqual(top("desk.ts", "export interface Desk { id: string }")["kind"], "interface")
        self.assertEqual(top("desk.tsx", "export enum Side { Left }")["kind"], "enum")
        self.assertEqual(top("desk.ts", "export default abstract class Desk {}")["kind"], "class")

    def test_a_file_exporting_several_types_or_none_has_no_declaration(self):
        self.assertIsNone(top("desk.ts", "export class A {}\nexport interface B {}\n"))
        self.assertIsNone(top("desk.ts", "export const a = 1;\n"))


class OtherFilesTest(unittest.TestCase):
    def test_a_file_of_another_language_has_no_declaration(self):
        self.assertIsNone(top("pom.xml", "<project>class</project>"))
        self.assertIsNone(top("README.md", "public class A {}"))


if __name__ == "__main__":
    unittest.main()
