"""What the review page's file tree shows left of a file's name: the kind and the visibility of the file's top-level
type, read from its text. Java, Groovy and Kotlin give both; TypeScript gives the kind of its one exported class,
interface or enum, without a visibility."""
import pathlib
import re

# strings first, so a comment marker inside a string is not taken for a comment, and the other way round
NOISE = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
                   r"|//[^\n]*|/\*(?:.|\n)*?\*/")
ANNOTATION = re.compile(r"@(?!interface\b)[\w.]+(?:\s*\((?:[^()]|\([^()]*\))*\))?")
JVM_TYPE = re.compile(r"((?:\b(?:public|protected|private|internal|abstract|static|final|sealed|non-sealed|strictfp|open|"
                      r"data|inner|value|enum|annotation|fun|expect|actual)\s+)*)"
                      r"(@interface|\b(?:class|interface|enum|record|trait|object))\s+(\w+)")
TS_EXPORT = re.compile(r"\bexport\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:const\s+)?(class|interface|enum)\b")
JVM = {".java": "package", ".groovy": "public", ".kt": "public"}  # the visibility of a type without a modifier
KINDS = {"@interface": "annotation", "trait": "interface", "object": "class"}
SUFFIXES = {*JVM, ".ts", ".tsx"}  # the files a type is read from


def top_level(path, text):
    """{"kind": class | interface | record | enum | annotation, "visibility": public | package | private | None}, or
    None for a file with no type of its own the tree can name."""
    suffix = pathlib.PurePath(path).suffix
    code = ANNOTATION.sub(" ", NOISE.sub(" ", text))
    if suffix in (".ts", ".tsx"):
        exported = TS_EXPORT.findall(code)
        return {"kind": exported[0], "visibility": None} if len(exported) == 1 else None
    if suffix not in JVM:
        return None
    found = list(JVM_TYPE.finditer(code))
    if not found:
        return None
    stem = pathlib.PurePath(path).stem
    chosen = next((m for m in found if m.group(3) == stem), found[0])
    modifiers = chosen.group(1).split()
    kind = ("enum" if "enum" in modifiers else "annotation" if "annotation" in modifiers
            else KINDS.get(chosen.group(2), chosen.group(2)))
    visibility = ("private" if "private" in modifiers else "public" if "public" in modifiers
                  else "package" if {"internal", "protected"} & set(modifiers) else JVM[suffix])
    return {"kind": kind, "visibility": visibility}
