"""
AST parser — tree-sitter wrapper for multi-language AST analysis.
Falls back gracefully if a language grammar is not installed.

Supported: Python, JavaScript, TypeScript, Java, Go
"""
import structlog
from typing import Optional

log = structlog.get_logger()

_PARSERS: dict = {}   # language -> tree_sitter.Parser


def _load_parser(language: str) -> Optional[object]:
    """Lazily load a tree-sitter parser for the given language."""
    if language in _PARSERS:
        return _PARSERS[language]

    try:
        import tree_sitter
        from tree_sitter import Language, Parser

        lang_map = {
            "python":     "tree_sitter_python",
            "javascript": "tree_sitter_javascript",
            "typescript": "tree_sitter_typescript",
            "java":       "tree_sitter_java",
            "go":         "tree_sitter_go",
        }

        module_name = lang_map.get(language)
        if not module_name:
            return None

        mod = __import__(module_name)
        lang = Language(mod.language())
        parser = Parser(lang)
        _PARSERS[language] = parser
        return parser

    except Exception as exc:
        log.warning("ast_parser.load_failed", language=language, error=str(exc))
        _PARSERS[language] = None
        return None


_EXT_LANG = {
    "py":   "python",
    "js":   "javascript",
    "jsx":  "javascript",
    "ts":   "typescript",
    "tsx":  "typescript",
    "java": "java",
    "go":   "go",
}


class ASTParser:
    """
    High-level API for tree-sitter AST queries.
    Methods return empty lists if the language grammar is unavailable.
    """

    def get_language(self, filename: str) -> Optional[str]:
        ext = filename.rsplit(".", 1)[-1].lower()
        return _EXT_LANG.get(ext)

    def parse(self, source: str, language: str) -> Optional[object]:
        """Parse source code and return the tree-sitter tree, or None."""
        parser = _load_parser(language)
        if not parser:
            return None
        try:
            return parser.parse(source.encode())
        except Exception as exc:
            log.warning("ast_parser.parse_error", language=language, error=str(exc))
            return None

    def get_function_names(self, source: str, language: str) -> list[str]:
        """Extract all function/method definition names from source."""
        tree = self.parse(source, language)
        if not tree:
            return []

        names = []
        query_strings = {
            "python":     "(function_definition name: (identifier) @name)",
            "javascript": "(function_declaration name: (identifier) @name)",
            "typescript": "(function_declaration name: (identifier) @name)",
            "java":       "(method_declaration name: (identifier) @name)",
            "go":         "(function_declaration name: (identifier) @name)",
        }
        qs = query_strings.get(language, "")
        if not qs:
            return []

        try:
            from tree_sitter import Language
            mod = __import__(f"tree_sitter_{language}")
            lang = Language(mod.language())
            query = lang.query(qs)
            captures = query.captures(tree.root_node)
            names = [node.text.decode() for node, _ in captures]
        except Exception as exc:
            log.warning("ast_parser.query_error", error=str(exc))

        return names

    def get_class_names(self, source: str, language: str) -> list[str]:
        """Extract all class definition names from source."""
        tree = self.parse(source, language)
        if not tree:
            return []

        query_strings = {
            "python":     "(class_definition name: (identifier) @name)",
            "javascript": "(class_declaration name: (identifier) @name)",
            "typescript": "(class_declaration name: (identifier) @name)",
            "java":       "(class_declaration name: (identifier) @name)",
        }
        qs = query_strings.get(language, "")
        if not qs:
            return []

        names = []
        try:
            from tree_sitter import Language
            mod = __import__(f"tree_sitter_{language}")
            lang = Language(mod.language())
            query = lang.query(qs)
            captures = query.captures(tree.root_node)
            names = [node.text.decode() for node, _ in captures]
        except Exception:
            pass
        return names
