#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyObfuscator - Obfuscateur de code Python avancé
Supporte le renommage de variables, la suppression de docstrings,
l'insertion de code mort, et un menu interactif.
"""

import argparse
import ast
import os
import sys
import random
import string


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
║          Python Obfuscator - by Mathis & Eitan               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

COLORS = {
    'RESET':   '\033[0m',
    'RED':     '\033[91m',
    'GREEN':   '\033[92m',
    'YELLOW':  '\033[93m',
    'BLUE':    '\033[94m',
    'MAGENTA': '\033[95m',
    'CYAN':    '\033[96m',
    'WHITE':   '\033[97m',
    'BOLD':    '\033[1m',
    'DIM':     '\033[2m',
}


def c(text, color):
    """Colorise du texte pour le terminal."""
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"


#  NOMS PROTÉGÉS

BUILTIN_NAMES = {
    # Fonctions built-in
    'print', 'range', 'len', 'int', 'str', 'list', 'dict', 'tuple', 'set',
    'float', 'bool', 'bytes', 'bytearray', 'memoryview', 'object', 'type',
    'enumerate', 'map', 'filter', 'zip', 'sum', 'min', 'max', 'abs',
    'any', 'all', 'sorted', 'reversed', 'open', 'input', 'eval', 'exec',
    'compile', 'repr', 'vars', 'dir', 'help', 'id', 'hash', 'hex', 'oct',
    'bin', 'ord', 'chr', 'ascii', 'format', 'round', 'pow', 'divmod',
    'isinstance', 'issubclass', 'callable', 'hasattr', 'getattr', 'setattr',
    'delattr', 'super', 'property', 'classmethod', 'staticmethod',
    'breakpoint', 'globals', 'locals', 'next', 'iter', 'slice',
    'complex', 'frozenset',

    # Exceptions courantes
    'Exception', 'BaseException', 'ValueError', 'TypeError', 'KeyError',
    'IndexError', 'AttributeError', 'ImportError', 'ModuleNotFoundError',
    'FileNotFoundError', 'IOError', 'OSError', 'RuntimeError',
    'StopIteration', 'GeneratorExit', 'SystemExit', 'KeyboardInterrupt',
    'ArithmeticError', 'ZeroDivisionError', 'OverflowError',
    'FloatingPointError', 'LookupError', 'NameError', 'UnboundLocalError',
    'SyntaxError', 'IndentationError', 'TabError', 'SystemError',
    'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError',
    'UnicodeTranslateError', 'Warning', 'UserWarning', 'DeprecationWarning',
    'PendingDeprecationWarning', 'RuntimeWarning', 'SyntaxWarning',
    'ResourceWarning', 'FutureWarning', 'ImportWarning', 'BytesWarning',
    'NotImplementedError', 'RecursionError', 'PermissionError',
    'ProcessLookupError', 'TimeoutError', 'ConnectionError',
    'BrokenPipeError', 'ConnectionAbortedError', 'ConnectionRefusedError',
    'ConnectionResetError', 'FileExistsError', 'InterruptedError',
    'IsADirectoryError', 'NotADirectoryError', 'ChildProcessError',
    'BlockingIOError', 'BufferError', 'EOFError', 'AssertionError',
    'StopAsyncIteration',

    # Constantes
    'None', 'True', 'False', 'NotImplemented', 'Ellipsis',
    '__all__', '__slots__',

    # Noms spéciaux
    'self', 'cls',
}

# Noms qui commencent par __ (dunder) sont toujours protégés
# Les noms importés sont collectés dynamiquement

#  COLLECTEUR DE NOMS PROTÉGÉS (phase 1 : analyse)

class ProtectedNameCollector(ast.NodeVisitor):
    """Parcourt l'AST pour collecter tous les noms qui ne doivent PAS
    être renommés : imports, noms de fonctions/classes, décorateurs,
    arguments de fonctions, noms globaux/nonlocal."""

    def __init__(self):
        self.protected = set()

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            # Pour "import os.path", on protège "os"
            self.protected.add(name.split('.')[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.protected.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.protected.add(node.name)
        # Protéger tous les arguments
        for arg in node.args.args:
            self.protected.add(arg.arg)
        for arg in node.args.posonlyargs:
            self.protected.add(arg.arg)
        for arg in node.args.kwonlyargs:
            self.protected.add(arg.arg)
        if node.args.vararg:
            self.protected.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.protected.add(node.args.kwarg.arg)
        # Protéger les décorateurs
        for decorator in node.decorator_list:
            self._collect_decorator_names(decorator)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.protected.add(node.name)
        for decorator in node.decorator_list:
            self._collect_decorator_names(decorator)
        self.generic_visit(node)

    def visit_Global(self, node):
        for name in node.names:
            self.protected.add(name)
        self.generic_visit(node)

    def visit_Nonlocal(self, node):
        for name in node.names:
            self.protected.add(name)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.protected.add(node.name)
        self.generic_visit(node)

    def _collect_decorator_names(self, node):
        if isinstance(node, ast.Name):
            self.protected.add(node.id)
        elif isinstance(node, ast.Attribute):
            self._collect_decorator_names(node.value)
        elif isinstance(node, ast.Call):
            self._collect_decorator_names(node.func)

#  RENOMMEUR DE VARIABLES (phase 2 : transformation)

class SafeVariableRenamer(ast.NodeTransformer):
    """Renomme UNIQUEMENT les variables locales/simples en évitant de
    casser les imports, fonctions, classes, arguments, attributs, etc."""

    def __init__(self, protected_names):
        self.protected = protected_names | BUILTIN_NAMES
        self.mapping = {}
        self.counter = 0

    def _get_obfuscated_name(self, original):
        if original not in self.mapping:
            self.mapping[original] = f"_O0O{self.counter:X}O0_"
            self.counter += 1
        return self.mapping[original]

    def visit_Name(self, node):
        self.generic_visit(node)
        name = node.id

        # Ne pas toucher aux noms protégés
        if name in self.protected:
            return node

        # Ne pas toucher aux noms dunder
        if name.startswith('__') and name.endswith('__'):
            return node

        # Ne pas toucher aux noms commençant par _ suivi de majuscule (convention privée de classe)
        if name.startswith('_') and len(name) > 1 and name[1].isupper():
            return node

        node.id = self._get_obfuscated_name(name)
        return node

    # Ne PAS transformer les arguments de fonctions
    def visit_FunctionDef(self, node):
        # On ne renomme pas le nom de la fonction
        # Mais on visite le corps
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return node

    def visit_Import(self, node):
        # Ne pas toucher aux imports
        return node

    def visit_ImportFrom(self, node):
        # Ne pas toucher aux imports
        return node

    def visit_Attribute(self, node):
        # Visiter la partie valeur (.value) mais ne PAS renommer l'attribut (.attr)
        node.value = self.visit(node.value)
        return node

#  SUPPRESSEUR DE DOCSTRINGS

class DocstringRemover(ast.NodeTransformer):
    """Supprime les docstrings des modules, classes et fonctions."""

    def _remove_docstring(self, node):
        if (node.body and
                isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
            # Si le corps est vide après suppression, ajouter pass
            if not node.body:
                node.body = [ast.Pass()]
        return node

    def visit_Module(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)

#  INSERTION DE CODE MORT (Dead Code Insertion)

class DeadCodeInserter(ast.NodeTransformer):
    """Insère du code mort (jamais exécuté) pour rendre la lecture
    plus difficile. Utilise des conditions toujours fausses."""

    def __init__(self):
        self.counter = 0

    def _make_dead_var_name(self):
        self.counter += 1
        return f"_x{self.counter:X}z_"

    def _make_dead_block(self):
        """Crée un bloc de code mort dans un if toujours faux."""
        dead_var = self._make_dead_var_name()
        # Condition toujours fausse : if 0 > 1:
        false_test = ast.Compare(
            left=ast.Constant(value=0),
            ops=[ast.Gt()],
            comparators=[ast.Constant(value=1)]
        )
        # Corps du bloc mort : assignation inutile
        dead_body = [
            ast.Assign(
                targets=[ast.Name(id=dead_var, ctx=ast.Store())],
                value=ast.BinOp(
                    left=ast.Constant(value=random.randint(100, 9999)),
                    op=ast.Add(),
                    right=ast.Constant(value=random.randint(100, 9999))
                ),
                lineno=0
            )
        ]
        return ast.If(test=false_test, body=dead_body, orelse=[])

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if len(node.body) >= 2:
            # Insérer un bloc mort au début du corps de la fonction
            dead = self._make_dead_block()
            node.body.insert(0, dead)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

#  FONCTIONS D'OBFUSCATION

def apply_variable_renaming(source_code):
    """Renomme les variables locales de manière sûre."""
    try:
        tree = ast.parse(source_code)

        # Phase 1 : collecter les noms protégés
        collector = ProtectedNameCollector()
        collector.visit(tree)

        # Phase 2 : renommer les variables non protégées
        tree = ast.parse(source_code)  # Re-parser pour un arbre propre
        renamer = SafeVariableRenamer(collector.protected)
        tree = renamer.visit(tree)
        ast.fix_missing_locations(tree)

        result = ast.unparse(tree)
        return result
    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur renommage variables : {e}")
        return source_code


def apply_docstring_removal(source_code):
    """Supprime les docstrings du code."""
    try:
        tree = ast.parse(source_code)
        remover = DocstringRemover()
        tree = remover.visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur suppression docstrings : {e}")
        return source_code


def apply_dead_code_insertion(source_code):
    """Insère du code mort pour compliquer la lecture."""
    try:
        tree = ast.parse(source_code)
        inserter = DeadCodeInserter()
        tree = inserter.visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur insertion code mort : {e}")
        return source_code


def fix_string_quotes(code):
    """Post-traitement : s'assure que les chaînes avec apostrophes
    sont correctement gérées. ast.unparse() gère déjà l'échappement,
    mais on vérifie la syntaxe finale."""
    try:
        # Vérifier que le résultat est du Python valide
        ast.parse(code)
        return code
    except SyntaxError:
        # En cas de problème, on tente de re-parser et re-unparse
        # ce qui force ast à corriger les quotes
        try:
            tree = ast.parse(code)
            return ast.unparse(tree)
        except Exception:
            return code


def obfuscate_content(content, options):
    """Applique les transformations d'obfuscation selon les options."""
    result = content

    if options.get('rename_vars', False):
        print(f"  {c('[*]', 'CYAN')} Renommage des variables...")
        result = apply_variable_renaming(result)

    if options.get('strip_docstrings', False):
        print(f"  {c('[*]', 'CYAN')} Suppression des docstrings...")
        result = apply_docstring_removal(result)

    if options.get('dead_code', False):
        print(f"  {c('[*]', 'CYAN')} Insertion de code mort...")
        result = apply_dead_code_insertion(result)

    # Post-traitement des strings
    result = fix_string_quotes(result)

    return result

#  TRAITEMENT DE FICHIERS

def process_file(input_file, output_file, options, stats=None):
    """Traite un fichier Python unique."""
    if stats is None:
        stats = {'success': 0, 'errors': 0}

    try:
        if not input_file.endswith('.py'):
            print(f"  {c('[!]', 'YELLOW')} Ignoré : {input_file} (pas un fichier .py)")
            return stats

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(input_file, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception:
                print(f"  {c('[-]', 'RED')} Erreur d'encodage : {input_file}")
                stats['errors'] += 1
                return stats

        if not content.strip():
            print(f"  {c('[!]', 'YELLOW')} Fichier vide : {input_file}")
            # Copier le fichier vide tel quel
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            stats['success'] += 1
            return stats

        try:
            ast.parse(content)
        except SyntaxError as e:
            print(f"  {c('[-]', 'RED')} Erreur de syntaxe dans {input_file} : {e}")
            stats['errors'] += 1
            return stats

        print(f"\n  {c('[>]', 'BLUE')} Traitement : {c(input_file, 'WHITE')}")
        obfuscated_content = obfuscate_content(content, options)

        # Vérifier que le code obfusqué est valide
        try:
            ast.parse(obfuscated_content)
        except SyntaxError as e:
            print(f"  {c('[-]', 'RED')} Code obfusqué invalide pour {input_file} : {e}")
            print(f"  {c('[!]', 'YELLOW')} Le fichier original sera copié tel quel.")
            obfuscated_content = content
            stats['errors'] += 1

        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(obfuscated_content)

        print(f"  {c('[+]', 'GREEN')} ✓ {input_file} -> {output_file}")
        stats['success'] += 1

    except Exception as e:
        print(f"  {c('[-]', 'RED')} Erreur de traitement sur {input_file} : {e}")
        stats['errors'] += 1

    return stats


def process_directory(input_dir, output_dir, options):
    """Traite tous les fichiers .py d'un dossier récursivement."""
    stats = {'success': 0, 'errors': 0}
    count = 0

    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.py'):
                count += 1
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, relative_path)
                stats = process_file(input_path, output_path, options, stats)

    return count, stats

#  MENU INTERACTIF

def print_menu_header():
    """Affiche le banner et l'en-tête du menu."""
    os.system('cls' if os.name == 'nt' else 'clear')
    print(c(BANNER, 'CYAN'))


def interactive_menu():
    """Menu interactif style tool Python."""
    print_menu_header()

    # Options par défaut
    options = {
        'rename_vars': True,
        'strip_docstrings': False,
        'dead_code': False,
    }

    option_labels = {
        'rename_vars': 'Renommage de variables (AST)',
        'strip_docstrings': 'Suppression des commentaires & docstrings',
        'dead_code': 'Insertion de code mort (Dead Code)',
    }

    option_keys = list(options.keys())

    while True:
        print(f"\n  {c('═══ OPTIONS D\'OBFUSCATION ═══', 'MAGENTA')}\n")

        for i, key in enumerate(option_keys, 1):
            status = c('ON ', 'GREEN') if options[key] else c('OFF', 'RED')
            print(f"    [{c(str(i), 'CYAN')}] [{status}] {option_labels[key]}")

        print(f"\n    [{c('S', 'YELLOW')}] Sélectionner tout")
        print(f"    [{c('D', 'YELLOW')}] Désélectionner tout")
        print(f"    [{c('C', 'GREEN')}] Continuer →")
        print(f"    [{c('Q', 'RED')}] Quitter")

        choice = input(f"\n  {c('>', 'CYAN')} Choix : ").strip().upper()

        if choice == 'Q':
            print(f"\n  {c('[*]', 'YELLOW')} Au revoir !\n")
            sys.exit(0)
        elif choice == 'C':
            # Au moins une option doit être activée
            if not any(options.values()):
                print(f"\n  {c('[!]', 'YELLOW')} Aucune option activée ! Activez au moins une option.")
                continue
            break
        elif choice == 'S':
            for key in option_keys:
                options[key] = True
        elif choice == 'D':
            for key in option_keys:
                options[key] = False
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(option_keys):
                key = option_keys[idx]
                options[key] = not options[key]
            else:
                print(f"  {c('[!]', 'YELLOW')} Option invalide.")
        else:
            print(f"  {c('[!]', 'YELLOW')} Choix invalide.")

    # Demander le chemin d'entrée
    print(f"\n  {c('═══ FICHIERS ═══', 'MAGENTA')}\n")

    while True:
        input_path = input(f"  {c('>', 'CYAN')} Fichier ou dossier source : ").strip()
        if not input_path:
            print(f"  {c('[!]', 'YELLOW')} Veuillez entrer un chemin.")
            continue
        # Supprimer les guillemets autour du chemin (drag & drop)
        input_path = input_path.strip('"').strip("'")
        if not os.path.exists(input_path):
            print(f"  {c('[-]', 'RED')} Le chemin '{input_path}' n'existe pas.")
            continue
        break

    # Chemin de sortie
    while True:
        default_output = _default_output(input_path)
        output_path = input(
            f"  {c('>', 'CYAN')} Dossier/fichier de sortie [{c(default_output, 'DIM')}] : "
        ).strip()
        if not output_path:
            output_path = default_output
        output_path = output_path.strip('"').strip("'")
        break

    return input_path, output_path, options


def _default_output(input_path):
    """Génère un chemin de sortie par défaut."""
    if os.path.isfile(input_path):
        base, ext = os.path.splitext(input_path)
        return f"{base}_obfuscated{ext}"
    else:
        return os.path.join(os.path.dirname(input_path), os.path.basename(input_path) + "_obfuscated")

#  POINT D'ENTRÉE

def run_obfuscation(input_path, output_path, options):
    """Exécute l'obfuscation sur le chemin donné."""
    # Résumé
    active_opts = [name for key, name in {
        'rename_vars': 'Renommage variables',
        'strip_docstrings': 'Suppression docstrings',
        'dead_code': 'Code mort',
    }.items() if options.get(key, False)]

    print(f"\n{'═' * 60}")
    print(f"  {c('OBFUSCATION EN COURS', 'BOLD')}")
    print(f"{'═' * 60}")
    print(f"  Entrée  : {c(input_path, 'WHITE')}")
    print(f"  Sortie  : {c(output_path, 'WHITE')}")
    print(f"  Options : {c(', '.join(active_opts), 'CYAN')}")
    print(f"{'═' * 60}")

    if os.path.isfile(input_path):
        if os.path.isdir(output_path):
            output_file = os.path.join(output_path, os.path.basename(input_path))
        else:
            output_file = output_path

        stats = process_file(input_path, output_file, options)
        print(f"\n  {c('Résumé', 'BOLD')} : {stats['success']} fichier(s) traité(s), "
              f"{stats['errors']} erreur(s)")

    elif os.path.isdir(input_path):
        count, stats = process_directory(input_path, output_path, options)
        print(f"\n  {c('Résumé', 'BOLD')} : {stats['success']}/{count} fichier(s) traité(s), "
              f"{stats['errors']} erreur(s)")

    print(f"\n{'═' * 60}")
    print(f"  {c('✓ Obfuscation terminée !', 'GREEN')}")
    print(f"{'═' * 60}\n")


def main():
    """Point d'entrée principal : mode CLI ou interactif."""

    # Si aucun argument => mode interactif
    if len(sys.argv) == 1:
        input_path, output_path, options = interactive_menu()
        run_obfuscation(input_path, output_path, options)
        return

    # Mode CLI (argparse)
    parser = argparse.ArgumentParser(
        description="PyObfuscator - Obfuscateur de code Python avancé.",
        epilog="Exemples d'utilisation :\n"
               "  python main.py -i source.py -o output.py\n"
               "  python main.py -i source.py -o output.py --rename-vars\n"
               "  python main.py -i src/ -o dist/ --rename-vars --strip-docstrings --dead-code\n"
               "\n"
               "  Mode interactif (sans arguments) :\n"
               "  python main.py",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-i', '--input', required=True,
                        help="Chemin vers le fichier ou dossier source.")
    parser.add_argument('-o', '--output', required=True,
                        help="Chemin vers le fichier ou dossier de destination.")

    parser.add_argument('--rename-vars', action='store_true',
                        help="Renommer les variables avec des noms obfusqués (recommandé).")
    parser.add_argument('--strip-docstrings', action='store_true',
                        help="Supprimer les commentaires et docstrings.")
    parser.add_argument('--dead-code', action='store_true',
                        help="Insérer du code mort pour compliquer la lecture.")
    parser.add_argument('--all', action='store_true',
                        help="Activer toutes les options d'obfuscation.")

    args = parser.parse_args()

    input_path = args.input
    output_path = args.output

    if not os.path.exists(input_path):
        print(f"  {c('[-]', 'RED')} Erreur : '{input_path}' n'existe pas.")
        sys.exit(1)

    options = {
        'rename_vars': args.rename_vars or args.all,
        'strip_docstrings': args.strip_docstrings or args.all,
        'dead_code': args.dead_code or args.all,
    }

    # Si aucune option spécifiée en CLI, activer au moins le renommage
    if not any(options.values()):
        options['rename_vars'] = True

    print(c(BANNER, 'CYAN'))
    run_obfuscation(input_path, output_path, options)


if __name__ == "__main__":
    main()