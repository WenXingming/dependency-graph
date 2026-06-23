#!/usr/bin/env python3
"""为常见源码文件生成文件级依赖关系图。"""

from __future__ import annotations

import argparse
import fnmatch
import html
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
}

CPP_HEADER_EXTENSIONS = {".h", ".hh", ".hpp", ".hxx"}
CPP_IMPLEMENTATION_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx"}
CPP_EXTENSIONS = CPP_HEADER_EXTENSIONS | CPP_IMPLEMENTATION_EXTENSIONS

DEFAULT_EXCLUDES = (
    ".git/**",
    "build/**",
    "cmake-build-*/**",
    "dist/**",
    "node_modules/**",
    "third_party/**",
    "vendor/**",
    "__pycache__/**",
)

TEST_EXCLUDES = (
    "test/**",
    "tests/**",
    "*/test/**",
    "*/tests/**",
    "*Test.*",
    "*Tests.*",
    "*_test.*",
    "test_*",
)

CPP_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', re.MULTILINE)
PY_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)(?:\s+as\s+\w+)?", re.MULTILINE)
PY_FROM_RE = re.compile(r"^\s*from\s+([.\w]+)\s+import\s+([\w*,\s]+)", re.MULTILINE)
JS_IMPORT_RE = re.compile(
    r"""(?:from\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\))"""
)


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def has_matching_header(path: Path, candidates: set[Path]) -> bool:
    return any(path.with_suffix(ext) in candidates for ext in CPP_HEADER_EXTENSIONS)


def collect_files(args: argparse.Namespace) -> list[Path]:
    root = args.root.resolve()
    includes = args.include or []
    excludes = list(DEFAULT_EXCLUDES) + list(args.exclude or [])
    if args.no_tests:
        excludes.extend(TEST_EXCLUDES)

    candidates: set[Path] = set()
    if includes:
        for pattern in includes:
            candidates.update(path for path in root.glob(pattern) if path.is_file())
    else:
        scopes = args.scope or ["."]
        for scope in scopes:
            base = (root / scope).resolve()
            if base.is_file():
                candidates.add(base)
            elif base.is_dir():
                candidates.update(path for path in base.rglob("*") if path.is_file())

    files = []
    for path in sorted(candidates):
        try:
            relative = rel(path, root)
        except ValueError:
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        if matches_any(relative, excludes):
            continue
        if (
            args.cpp_view == "headers"
            and path.suffix in CPP_IMPLEMENTATION_EXTENSIONS
            and has_matching_header(path, candidates)
        ):
            continue
        files.append(path)
    return files


def build_indexes(files: list[Path], root: Path) -> tuple[set[str], dict[str, list[str]]]:
    file_set = {rel(path, root) for path in files}
    by_basename: dict[str, list[str]] = defaultdict(list)
    for path in files:
        by_basename[path.name].append(rel(path, root))
    return file_set, by_basename


def resolve_existing(path: Path, root: Path, file_set: set[str]) -> str | None:
    if path.is_file():
        try:
            candidate = rel(path, root)
        except ValueError:
            return None
        if candidate in file_set:
            return candidate
    return None


def resolve_cpp_include(
    include: str,
    source: Path,
    root: Path,
    file_set: set[str],
    by_basename: dict[str, list[str]],
) -> str | None:
    direct = resolve_existing((source.parent / include).resolve(), root, file_set)
    if direct:
        return direct

    from_root = resolve_existing((root / include).resolve(), root, file_set)
    if from_root:
        return from_root

    basename_matches = by_basename.get(Path(include).name, [])
    if len(basename_matches) == 1:
        return basename_matches[0]
    return None


def resolve_python_module(module: str, root: Path, file_set: set[str]) -> str | None:
    if not module or module.startswith("."):
        return None
    module_path = Path(*module.split("."))
    candidates = [
        root / module_path.with_suffix(".py"),
        root / module_path / "__init__.py",
    ]
    for candidate in candidates:
        resolved = resolve_existing(candidate.resolve(), root, file_set)
        if resolved:
            return resolved
    return None


def resolve_js_module(specifier: str, source: Path, root: Path, file_set: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    base = (source.parent / specifier).resolve()
    candidates = [base]
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"):
        candidates.append(base.with_suffix(ext))
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidates.append(base / f"index{ext}")

    for candidate in candidates:
        resolved = resolve_existing(candidate, root, file_set)
        if resolved:
            return resolved
    return None


def add_edge(edges: set[tuple[str, str]], source: str, target: str | None, external: bool, label: str) -> None:
    if target:
        edges.add((source, target))
    elif external:
        edges.add((source, f"external:{label}"))


def extract_edges(
    files: list[Path],
    root: Path,
    external: bool,
    file_set: set[str],
    by_basename: dict[str, list[str]],
) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for path in files:
        source = rel(path, root)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if path.suffix in CPP_EXTENSIONS:
            for delimiter, include in CPP_INCLUDE_RE.findall(text):
                target = resolve_cpp_include(include, path, root, file_set, by_basename)
                if target or delimiter == '"' or external:
                    add_edge(edges, source, target, external and delimiter == "<", include)

        if path.suffix == ".py":
            for module in PY_IMPORT_RE.findall(text):
                add_edge(edges, source, resolve_python_module(module, root, file_set), external, module)
            for module, imported in PY_FROM_RE.findall(text):
                target = resolve_python_module(module, root, file_set)
                add_edge(edges, source, target, external and not module.startswith("."), module or imported)

        if path.suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            for groups in JS_IMPORT_RE.findall(text):
                specifier = next((item for item in groups if item), "")
                target = resolve_js_module(specifier, path, root, file_set)
                add_edge(edges, source, target, external and not specifier.startswith("."), specifier)

    return edges


def find_cycles(nodes: set[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        if target.startswith("external:"):
            continue
        adjacency[source].append(target)

    index = 0
    stack: list[str] = []
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency[node]:
            if neighbor not in indexes:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[neighbor])

        if lowlinks[node] == indexes[node]:
            component: list[str] = []
            while True:
                current = stack.pop()
                on_stack.remove(current)
                component.append(current)
                if current == node:
                    break
            if len(component) > 1:
                cycles.append(sorted(component))

    for node in sorted(nodes):
        if node not in indexes:
            strongconnect(node)
    return cycles


def build_graph_data(root: Path, files: list[Path], edges: set[tuple[str, str]], args: argparse.Namespace) -> dict:
    nodes = {rel(path, root) for path in files}
    for source, target in edges:
        nodes.add(source)
        nodes.add(target)

    fan_in = Counter(target for _, target in edges)
    fan_out = Counter(source for source, _ in edges)
    return {
        "root": root.as_posix(),
        "cpp_view": args.cpp_view,
        "direction": args.direction,
        "nodes": sorted(nodes),
        "edges": [{"source": source, "target": target} for source, target in sorted(edges)],
        "fan_in": dict(sorted(fan_in.items())),
        "fan_out": dict(sorted(fan_out.items())),
        "cycles": find_cycles(nodes, edges),
    }


def dot_id(value: str) -> str:
    return json.dumps(value)


def render_dot(data: dict) -> str:
    lines = [
        "digraph dependencies {",
        f"  graph [rankdir={data['direction']}, overlap=false, splines=true, bgcolor=\"white\"];",
        "  node [shape=box, style=\"rounded,filled\", fillcolor=\"#f8fafc\", color=\"#64748b\", fontname=\"Helvetica\", fontsize=11];",
        "  edge [color=\"#475569\", arrowsize=0.8];",
    ]
    for node in data["nodes"]:
        fill = "#f1f5f9" if node.startswith("external:") else "#f8fafc"
        color = "#94a3b8" if node.startswith("external:") else "#64748b"
        label = node.removeprefix("external:")
        lines.append(f"  {dot_id(node)} [label={dot_id(label)}, fillcolor={dot_id(fill)}, color={dot_id(color)}];")
    for edge in data["edges"]:
        style = " [style=dashed, color=\"#94a3b8\"]" if edge["target"].startswith("external:") else ""
        lines.append(f"  {dot_id(edge['source'])} -> {dot_id(edge['target'])}{style};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_mermaid(data: dict) -> str:
    node_ids = {node: f"N{i}" for i, node in enumerate(data["nodes"])}
    lines = [f"flowchart {data['direction']}"]
    for node, node_id in node_ids.items():
        label = node.removeprefix("external:").replace('"', "'")
        lines.append(f'  {node_id}["{label}"]')
    for edge in data["edges"]:
        lines.append(f"  {node_ids[edge['source']]} --> {node_ids[edge['target']]}")
    return "\n".join(lines) + "\n"


def render_svg(dot_text: str, output: Path) -> None:
    if not shutil.which("dot"):
        raise RuntimeError("输出 SVG 需要 Graphviz 的 dot 命令。可以改为输出 .dot 或 .mmd。")
    subprocess.run(["dot", "-Tsvg", "-o", output.as_posix()], input=dot_text, text=True, check=True)


def render_html(data: dict, dot_text: str) -> str:
    svg = ""
    if shutil.which("dot"):
        result = subprocess.run(["dot", "-Tsvg"], input=dot_text, text=True, check=True, capture_output=True)
        svg = result.stdout
    else:
        svg = f"<pre>{html.escape(render_mermaid(data))}</pre>"

    edge_rows = "\n".join(
        f"<tr><td>{html.escape(edge['source'])}</td><td>{html.escape(edge['target'])}</td></tr>"
        for edge in data["edges"]
    )
    cycles = "无" if not data["cycles"] else html.escape(json.dumps(data["cycles"], ensure_ascii=False))
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>文件依赖关系图</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #0f172a; }}
.graph {{ overflow: auto; border: 1px solid #cbd5e1; padding: 16px; }}
table {{ border-collapse: collapse; margin-top: 20px; width: 100%; }}
td, th {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
th {{ background: #f8fafc; }}
code {{ background: #f1f5f9; padding: 2px 4px; }}
</style>
<h1>文件依赖关系图</h1>
<p><strong>节点：</strong> {len(data["nodes"])} <strong>边：</strong> {len(data["edges"])} <strong>循环：</strong> <code>{cycles}</code> <strong>方向：</strong> <code>{html.escape(data["direction"])}</code> <strong>C/C++ 视图：</strong> <code>{html.escape(data["cpp_view"])}</code></p>
<div class="graph">{svg}</div>
<h2>依赖边</h2>
<table><thead><tr><th>使用者文件</th><th>被依赖文件</th></tr></thead><tbody>{edge_rows}</tbody></table>
</html>
"""


def write_output(data: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    dot_text = render_dot(data)

    if suffix == ".json":
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif suffix == ".dot":
        output.write_text(dot_text, encoding="utf-8")
    elif suffix == ".mmd":
        output.write_text(render_mermaid(data), encoding="utf-8")
    elif suffix == ".svg":
        render_svg(dot_text, output)
    elif suffix in {".html", ".htm"}:
        output.write_text(render_html(data, dot_text), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported output extension: {output.suffix}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path, help="仓库根目录，默认是当前目录。")
    parser.add_argument("--scope", action="append", help="要扫描的目录或文件，可重复传入。")
    parser.add_argument("--include", action="append", help="相对 root 的包含 glob，可重复传入。")
    parser.add_argument("--exclude", action="append", help="相对 root 的排除 glob，可重复传入。")
    parser.add_argument("--output", type=Path, help="输出文件：.svg、.dot、.mmd、.html 或 .json。")
    parser.add_argument("--json", type=Path, help="额外输出原始图数据 JSON。")
    parser.add_argument("--external", action="store_true", help="包含未解析到项目内文件的外部/系统依赖。")
    parser.add_argument("--no-tests", action="store_true", help="排除常见测试目录和测试文件。")
    parser.add_argument(
        "--cpp-view",
        choices=("headers", "all"),
        default="headers",
        help="C/C++ 视图。headers 表示同名 .h/.cpp 同时存在时只展示头文件；all 表示展示所有源码文件。",
    )
    parser.add_argument(
        "--direction",
        choices=("TB", "LR", "BT", "RL"),
        default="TB",
        help="图布局方向。TB 为自上而下，LR 为自左向右。",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    files = collect_files(args)
    file_set, by_basename = build_indexes(files, root)
    edges = extract_edges(files, root, args.external, file_set, by_basename)
    data = build_graph_data(root, files, edges, args)

    if args.output:
        write_output(data, args.output)
    if args.json:
        write_output(data, args.json)
    if not args.output and not args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"节点={len(data['nodes'])} 边={len(data['edges'])} 循环={len(data['cycles'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
