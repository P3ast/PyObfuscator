#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyObfuscator - Obfuscateur de code Python avancé
Supporte le renommage de variables/fonctions, la suppression de docstrings,
l'insertion de code mort, et un menu interactif.
"""

import argparse
import ast
import builtins
import copy
import os
import sys
import random

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ██╗   ██╗ ██████╗ ██████╗ ███████╗                ║
║   ██╔══██╗╚██╗ ██╔╝██╔═══██╗██╔══██╗██╔════╝                ║
║   ██████╔╝ ╚████╔╝ ██║   ██║██████╔╝█████╗                  ║
║   ██╔═══╝   ╚██╔╝  ██║   ██║██╔══██╗██╔══╝                  ║
║   ██║        ██║   ╚██████╔╝██████╔╝██║                      ║
║   ╚═╝        ╚═╝    ╚═════╝ ╚═════╝ ╚═╝                      ║
║                                                              ║
║                    Python Obfuscator                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

COLORS = {
    'RESET': '\033[0m',  'RED':    '\033[91m', 'GREEN':  '\033[92m',
    'YELLOW': '\033[93m', 'BLUE':   '\033[94m', 'MAGENTA': '\033[95m',
    'CYAN':  '\033[96m', 'WHITE':  '\033[97m', 'BOLD':   '\033[1m',
    'DIM':   '\033[2m',
}

BUILTIN_NAMES = set(dir(builtins)) | {
    'self', 'cls', '__all__', '__slots__',
    'None', 'True', 'False', 'NotImplemented', 'Ellipsis',
}

# (clé, label menu, défaut, flag CLI)
OBFUSCATION_OPTIONS = [
    ('rename_vars',      'Renommage de variables (AST)',             True,  '--rename-vars'),
    ('rename_funcs',     'Renommage des fonctions & arguments',      False, '--rename-funcs'),
    ('strip_docstrings', 'Suppression des commentaires & docstrings', False, '--strip-docstrings'),
    ('dead_code',        'Insertion de code mort (Dead Code)',        False, '--dead-code'),
]


def c(text, color):
    """Colorise du texte pour le terminal."""
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"


def _is_dunder(name):
    return name.startswith('__') and name.endswith('__')


def _collect_all_args(args_node):
    """Retourne tous les noms d'arguments d'un noeud arguments."""
    names = [a.arg for lst in (args_node.args, args_node.posonlyargs,
                               args_node.kwonlyargs) for a in lst]
    if args_node.vararg:
        names.append(args_node.vararg.arg)
    if args_node.kwarg:
        names.append(args_node.kwarg.arg)
    return names


# ── COLLECTEUR UNIFIÉ (phase 1 : analyse) ──

class ASTCollector(ast.NodeVisitor):
    """Parcourt l'AST une seule fois pour collecter :
    - protected : noms à ne jamais renommer (imports, classes, décorateurs…)
    - functions : {nom_func: [arg_names]} pour les fonctions hors classe
    """

    def __init__(self):
        self.protected = set()
        self.functions = {}
        self._in_class = False

    def _collect_decorator_names(self, node):
        if isinstance(node, ast.Name):
            self.protected.add(node.id)
        elif isinstance(node, ast.Attribute):
            self._collect_decorator_names(node.value)
        elif isinstance(node, ast.Call):
            self._collect_decorator_names(node.func)

    def visit_Import(self, node):
        for alias in node.names:
            self.protected.add((alias.asname or alias.name).split('.')[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.protected.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.protected.add(node.name)
        all_args = _collect_all_args(node.args)
        for a in all_args:
            self.protected.add(a)
        for deco in node.decorator_list:
            self._collect_decorator_names(deco)
        # Collecter en tant que fonction renommable (hors classe)
        if not self._in_class and node.name not in BUILTIN_NAMES and not _is_dunder(node.name):
            renamable = [a for a in all_args
                         if a not in BUILTIN_NAMES and a not in ('self', 'cls') and not _is_dunder(a)]
            self.functions[node.name] = renamable
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.protected.add(node.name)
        for deco in node.decorator_list:
            self._collect_decorator_names(deco)
        old = self._in_class
        self._in_class = True
        self.generic_visit(node)
        self._in_class = old

    def visit_Global(self, node):
        self.protected.update(node.names)
        self.generic_visit(node)

    def visit_Nonlocal(self, node):
        self.protected.update(node.names)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.protected.add(node.name)
        self.generic_visit(node)


# ── RENOMMEUR DE VARIABLES ──

class SafeVariableRenamer(ast.NodeTransformer):
    """Renomme uniquement les variables locales/simples."""

    def __init__(self, protected_names):
        self.protected = protected_names | BUILTIN_NAMES
        self.mapping = {}
        self.counter = 0

    def _obf(self, name):
        if name not in self.mapping:
            self.mapping[name] = f"_O0O{self.counter:X}O0_"
            self.counter += 1
        return self.mapping[name]

    def visit_Name(self, node):
        self.generic_visit(node)
        n = node.id
        if n in self.protected or _is_dunder(n):
            return node
        if n.startswith('_') and len(n) > 1 and n[1].isupper():
            return node
        node.id = self._obf(n)
        return node

    def visit_Import(self, node):
        return node

    def visit_ImportFrom(self, node):
        return node

    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        return node


# ── RENOMMEUR DE FONCTIONS & ARGUMENTS ──

class FuncArgRenamer(ast.NodeTransformer):
    """Renomme les noms de fonctions et leurs arguments de manière cohérente."""

    def __init__(self, func_mapping, func_arg_mappings):
        self.func_mapping = func_mapping
        self.func_arg_mappings = func_arg_mappings
        self.arg_stack = []
        self._in_class = False

    def visit_ClassDef(self, node):
        old = self._in_class
        self._in_class = True
        self.generic_visit(node)
        self._in_class = old
        return node

    def visit_FunctionDef(self, node):
        orig = node.name
        if not self._in_class and orig in self.func_mapping:
            node.name = self.func_mapping[orig]
        am = self.func_arg_mappings.get(orig, {})
        # Renommer les arguments dans la signature
        for arg_list in (node.args.args, node.args.posonlyargs, node.args.kwonlyargs):
            for a in arg_list:
                if a.arg in am:
                    a.arg = am[a.arg]
        if node.args.vararg and node.args.vararg.arg in am:
            node.args.vararg.arg = am[node.args.vararg.arg]
        if node.args.kwarg and node.args.kwarg.arg in am:
            node.args.kwarg.arg = am[node.args.kwarg.arg]
        self.arg_stack.append(am)
        self.generic_visit(node)
        self.arg_stack.pop()
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node):
        for mapping in reversed(self.arg_stack):
            if node.id in mapping:
                node.id = mapping[node.id]
                return node
        if node.id in self.func_mapping:
            node.id = self.func_mapping[node.id]
        return node

    def visit_Call(self, node):
        orig_func = None
        if isinstance(node.func, ast.Name) and node.func.id in self.func_arg_mappings:
            orig_func = node.func.id
        self.generic_visit(node)
        if orig_func:
            am = self.func_arg_mappings[orig_func]
            for kw in node.keywords:
                if kw.arg and kw.arg in am:
                    kw.arg = am[kw.arg]
        return node

    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        return node


# ── SUPPRESSEUR DE DOCSTRINGS ──

class DocstringRemover(ast.NodeTransformer):
    """Supprime les docstrings des modules, classes et fonctions."""

    def _strip(self, node):
        self.generic_visit(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    visit_Module = visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _strip


# ── INSERTION DE CODE MORT ──

class DeadCodeInserter(ast.NodeTransformer):
    """Insère des blocs de code mort (jamais exécutés) dans les fonctions."""

    def __init__(self):
        self.counter = 0

    def _dead_block(self):
        self.counter += 1
        return ast.If(
            test=ast.Compare(left=ast.Constant(0), ops=[ast.Gt()],
                             comparators=[ast.Constant(1)]),
            body=[ast.Assign(
                targets=[ast.Name(id=f"_x{self.counter:X}z_", ctx=ast.Store())],
                value=ast.BinOp(left=ast.Constant(random.randint(100, 9999)),
                                op=ast.Add(),
                                right=ast.Constant(random.randint(100, 9999))),
                lineno=0)],
            orelse=[])

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if len(node.body) >= 2:
            node.body.insert(0, self._dead_block())
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


# ── FONCTIONS D'OBFUSCATION ──

def _safe_transform(source_code, transform_fn, label):
    """Parse → transforme → re-génère le code, avec gestion d'erreur."""
    try:
        tree = ast.parse(source_code)
        tree = transform_fn(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur {label} : {e}")
        return source_code


def apply_variable_renaming(source_code):
    """Renomme les variables locales de manière sûre."""
    def transform(tree):
        collector = ASTCollector()
        collector.visit(tree)
        tree_copy = copy.deepcopy(tree)
        return SafeVariableRenamer(collector.protected).visit(tree_copy)
    return _safe_transform(source_code, transform, 'renommage variables')


def apply_func_arg_renaming(source_code):
    """Renomme les fonctions (hors classes) et leurs arguments."""
    def transform(tree):
        collector = ASTCollector()
        collector.visit(tree)
        counter = 0
        fm, fam = {}, {}
        for fname, args in collector.functions.items():
            fm[fname] = f"_0x{counter:X}_"
            counter += 1
            am = {}
            for aname in args:
                am[aname] = f"_0x{counter:X}_"
                counter += 1
            fam[fname] = am
        tree_copy = copy.deepcopy(tree)
        return FuncArgRenamer(fm, fam).visit(tree_copy)
    return _safe_transform(source_code, transform, 'renommage fonctions/arguments')


# Pipeline d'obfuscation
PIPELINE = [
    ('rename_vars',      'Renommage des variables',    lambda s: apply_variable_renaming(s)),
    ('rename_funcs',     'Renommage fonctions/args',   lambda s: apply_func_arg_renaming(s)),
    ('strip_docstrings', 'Suppression des docstrings',
     lambda s: _safe_transform(s, lambda t: DocstringRemover().visit(t), 'suppression docstrings')),
    ('dead_code',        'Insertion de code mort',
     lambda s: _safe_transform(s, lambda t: DeadCodeInserter().visit(t), 'insertion code mort')),
]


def obfuscate_content(content, options):
    """Applique les transformations d'obfuscation selon les options."""
    result = content
    for key, label, transform in PIPELINE:
        if options.get(key):
            print(f"  {c('[*]', 'CYAN')} {label}...")
            result = transform(result)
    return result


# ── TRAITEMENT DE FICHIERS ──

def _read_file(filepath):
    """Lit un fichier avec fallback d'encodage."""
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return None


def _write_file(filepath, content):
    """Écrit du contenu en créant les dossiers parents si nécessaire."""
    d = os.path.dirname(filepath)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def process_file(input_file, output_file, options, stats=None):
    """Traite un fichier Python unique."""
    if stats is None:
        stats = {'success': 0, 'errors': 0}
    try:
        if not input_file.endswith('.py'):
            print(f"  {c('[!]', 'YELLOW')} Ignoré : {input_file} (pas un .py)")
            return stats

        content = _read_file(input_file)
        if content is None:
            print(f"  {c('[-]', 'RED')} Erreur d'encodage : {input_file}")
            stats['errors'] += 1
            return stats

        if not content.strip():
            _write_file(output_file, content)
            stats['success'] += 1
            return stats

        try:
            ast.parse(content)
        except SyntaxError as e:
            print(f"  {c('[-]', 'RED')} Erreur de syntaxe dans {input_file} : {e}")
            stats['errors'] += 1
            return stats

        print(f"\n  {c('[>]', 'BLUE')} Traitement : {c(input_file, 'WHITE')}")
        result = obfuscate_content(content, options)

        try:
            ast.parse(result)
        except SyntaxError:
            print(f"  {c('[-]', 'RED')} Code obfusqué invalide, copie du fichier original.")
            result = content
            stats['errors'] += 1

        _write_file(output_file, result)
        print(f"  {c('[+]', 'GREEN')} ✓ {input_file} -> {output_file}")
        stats['success'] += 1

    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur sur {input_file} : {e}")
        stats['errors'] += 1
    return stats


def process_directory(input_dir, output_dir, options):
    """Traite tous les fichiers .py d'un dossier récursivement."""
    stats, count = {'success': 0, 'errors': 0}, 0
    for root, _, files in os.walk(input_dir):
        for f in files:
            if f.endswith('.py'):
                count += 1
                inp = os.path.join(root, f)
                out = os.path.join(output_dir, os.path.relpath(inp, input_dir))
                stats = process_file(inp, out, options, stats)
    return count, stats


# ── MENU INTERACTIF ──

def interactive_menu():
    """Menu interactif style tool Python."""
    os.system('cls' if os.name == 'nt' else 'clear')
    print(c(BANNER, 'CYAN'))

    options = {key: default for key, _, default, _ in OBFUSCATION_OPTIONS}
    labels = {key: label for key, label, _, _ in OBFUSCATION_OPTIONS}
    keys = list(options.keys())

    while True:
        print(f"\n  {c('═══ OPTIONS D\'OBFUSCATION ═══', 'MAGENTA')}\n")
        for i, key in enumerate(keys, 1):
            st = c('ON ', 'GREEN') if options[key] else c('OFF', 'RED')
            print(f"    [{c(str(i), 'CYAN')}] [{st}] {labels[key]}")

        print(f"\n    [{c('S', 'YELLOW')}] Sélectionner tout")
        print(f"    [{c('D', 'YELLOW')}] Désélectionner tout")
        print(f"    [{c('C', 'GREEN')}] Continuer →")
        print(f"    [{c('Q', 'RED')}] Quitter")

        choice = input(f"\n  {c('>', 'CYAN')} Choix : ").strip().upper()

        if choice == 'Q':
            print(f"\n  {c('[*]', 'YELLOW')} Au revoir !\n")
            sys.exit(0)
        elif choice == 'C':
            if not any(options.values()):
                print(f"\n  {c('[!]', 'YELLOW')} Activez au moins une option.")
                continue
            break
        elif choice == 'S':
            options = {k: True for k in keys}
        elif choice == 'D':
            options = {k: False for k in keys}
        elif choice.isdigit() and 0 <= int(choice) - 1 < len(keys):
            k = keys[int(choice) - 1]
            options[k] = not options[k]
        else:
            print(f"  {c('[!]', 'YELLOW')} Choix invalide.")

    # Chemin d'entrée
    print(f"\n  {c('═══ FICHIERS ═══', 'MAGENTA')}\n")
    while True:
        input_path = input(f"  {c('>', 'CYAN')} Fichier ou dossier source : ").strip().strip('"').strip("'")
        if not input_path:
            print(f"  {c('[!]', 'YELLOW')} Veuillez entrer un chemin.")
        elif not os.path.exists(input_path):
            print(f"  {c('[-]', 'RED')} Le chemin '{input_path}' n'existe pas.")
        else:
            break

    # Chemin de sortie
    default_out = _default_output(input_path)
    output_path = input(
        f"  {c('>', 'CYAN')} Sortie [{c(default_out, 'DIM')}] : "
    ).strip().strip('"').strip("'") or default_out

    return input_path, output_path, options


def _default_output(path):
    if os.path.isfile(path):
        base, ext = os.path.splitext(path)
        return f"{base}_obfuscated{ext}"
    return path + "_obfuscated"


# ── POINT D'ENTRÉE ──

def run_obfuscation(input_path, output_path, options):
    """Exécute l'obfuscation sur le chemin donné."""
    active = [label for key, label, _, _ in OBFUSCATION_OPTIONS if options.get(key)]

    sep = '═' * 60
    print(f"\n{sep}\n  {c('OBFUSCATION EN COURS', 'BOLD')}\n{sep}")
    print(f"  Entrée  : {c(input_path, 'WHITE')}")
    print(f"  Sortie  : {c(output_path, 'WHITE')}")
    print(f"  Options : {c(', '.join(active), 'CYAN')}\n{sep}")

    if os.path.isfile(input_path):
        out = os.path.join(output_path, os.path.basename(input_path)) if os.path.isdir(output_path) else output_path
        stats = process_file(input_path, out, options)
        print(f"\n  {c('Résumé', 'BOLD')} : {stats['success']} fichier(s), {stats['errors']} erreur(s)")
    elif os.path.isdir(input_path):
        count, stats = process_directory(input_path, output_path, options)
        print(f"\n  {c('Résumé', 'BOLD')} : {stats['success']}/{count} fichier(s), {stats['errors']} erreur(s)")

    print(f"\n{sep}\n  {c('✓ Obfuscation terminée !', 'GREEN')}\n{sep}\n")


def main():
    """Point d'entrée principal : mode CLI ou interactif."""
    if len(sys.argv) == 1:
        inp, out, opts = interactive_menu()
        run_obfuscation(inp, out, opts)
        return

    parser = argparse.ArgumentParser(
        description="PyObfuscator - Obfuscateur de code Python avancé.",
        epilog="Exemples :\n"
               "  python main.py -i source.py -o output.py --all\n"
               "  python main.py -i src/ -o dist/ --rename-vars --rename-funcs\n"
               "\n  Mode interactif : python main.py",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-i', '--input', required=True, help="Fichier ou dossier source.")
    parser.add_argument('-o', '--output', required=True, help="Fichier ou dossier de destination.")
    for key, label, _, flag in OBFUSCATION_OPTIONS:
        parser.add_argument(flag, action='store_true', help=label)
    parser.add_argument('--all', action='store_true', help="Activer toutes les options.")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"  {c('[-]', 'RED')} Erreur : '{args.input}' n'existe pas.")
        sys.exit(1)

    # Construire les options depuis la config centralisée
    options = {key: getattr(args, key.replace('-', '_')) or args.all
               for key, _, _, _ in OBFUSCATION_OPTIONS}
    if not any(options.values()):
        options['rename_vars'] = True

    print(c(BANNER, 'CYAN'))
    run_obfuscation(args.input, args.output, options)


if __name__ == "__main__":
    main()