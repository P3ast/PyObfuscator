# PyObfuscator

```
  ██████╗ ██╗   ██╗ ██████╗ ██████╗ ███████╗
  ██╔══██╗╚██╗ ██╔╝██╔═══██╗██╔══██╗██╔════╝
  ██████╔╝ ╚████╔╝ ██║   ██║██████╔╝█████╗  
  ██╔═══╝   ╚██╔╝  ██║   ██║██╔══██╗██╔══╝  
  ██║        ██║   ╚██████╔╝██████╔╝██║     
  ╚═╝        ╚═╝    ╚═════╝ ╚═════╝ ╚═╝     
```

Obfuscateur de code Python basé sur la manipulation de l'AST (Abstract Syntax Tree).

Le principe : le code Python conserve exactement le même comportement, mais devient illisible pour quiconque essaie de le lire ou de le reverse-engineering.

## Contexte

Python étant un langage interprété, le code source est directement accessible. PyObfuscator permet de transformer ce code via l'AST pour le rendre incompréhensible, tout en préservant son fonctionnement.

## Fonctionnalités

L'outil propose 4 transformations, activables individuellement :

- **Renommage de variables** — Les variables locales sont remplacées par des identifiants comme `_O0O0O0_`, `_O0O1O0_`, etc. Les imports, builtins et attributs restent intacts.
- **Renommage de fonctions & arguments** — Les noms de fonctions et leurs paramètres deviennent `_0x0_`, `_0x1_`, etc. Les méthodes de classe sont exclues pour éviter de casser les appels `self.method()`.
- **Suppression des docstrings** — Retire les docstrings des modules, classes et fonctions.
- **Insertion de code mort** — Ajoute des blocs `if 0 > 1:` contenant des opérations inutiles dans le corps des fonctions, afin de compliquer la lecture.
- **Aplatissement du flux** (Control Flow Flattening) — Détruit la structure d'exécution linéaire des fonctions en plaçant les instructions dans une grande boucle while contrôlée par un routeur if/elif et une variable d'état générée aléatoirement.

## Installation

Aucune dépendance externe, uniquement la bibliothèque standard Python.

```bash
git clone https://github.com/P3ast/PyObfuscator.git
cd PyObfuscator
```

Nécessite Python 3.9 ou supérieur.

## Utilisation

### Mode interactif

```bash
python main.py
```

Sans arguments, un menu s'affiche permettant de sélectionner les options souhaitées et de renseigner les chemins d'entrée/sortie.

### Mode CLI

```bash
# Activer toutes les options
python main.py -i source.py -o output.py --all

# Renommage des variables uniquement
python main.py -i source.py -o output.py --rename-vars

# Variables + fonctions/arguments + flattening
python main.py -i source.py -o output.py --rename-vars --rename-funcs --flatten

# Obfusquer un dossier entier (récursif)
python main.py -i mon_projet/ -o mon_projet_obf/ --all
```

### Arguments disponibles

| Argument | Description |
|----------|-------------|
| `-i`, `--input` | Fichier ou dossier source |
| `-o`, `--output` | Fichier ou dossier de sortie |
| `--rename-vars` | Renommage des variables |
| `--rename-funcs` | Renommage des fonctions & arguments |
| `--strip-docstrings` | Suppression des docstrings |
| `--dead-code` | Insertion de code mort |
| `--flatten` | Aplatissement du flux (Control Flow Flattening) |
| `--all` | Active toutes les options |

## Exemple

Avant :

```python
def calculer_interet(montant, taux, annees):
    """Calcule l'intérêt composé simple."""
    resultat = montant
    compteur = 0
    while compteur < annees:
        resultat = resultat * (1 + taux / 100)
        compteur += 1
    return round(resultat, 2)

def main():
    capital_initial = 1000
    final = calculer_interet(capital_initial, 5, 3)
    print(f"Capital : {final}€")

if __name__ == "__main__":
    main()
```

Après (`--all`) :

```python
def _0x0_(_0x1_, _0x2_, _0x3_):
    if 0 > 1:
        _x1z_ = 8039 + 1957
    _O0O0O0_ = _0x1_
    _O0O1O0_ = 0
    while _O0O1O0_ < _0x3_:
        _O0O0O0_ = _O0O0O0_ * (1 + _0x2_ / 100)
        _O0O1O0_ += 1
    return round(_O0O0O0_, 2)

def _0x6_():
    if 0 > 1:
        _x3z_ = 9292 + 1467
    _O0O4O0_ = 1000
    _O0O7O0_ = _0x0_(_O0O4O0_, 5, 3)
    print(f'Capital : {_O0O7O0_}€')

if __name__ == '__main__':
    _0x6_()
```

Les deux versions produisent le même résultat à l'exécution.

## Fonctionnement interne

Le programme repose sur le module `ast` de Python pour parser le code source en arbre syntaxique, puis appliquer des transformations successives :

1. `ast.parse()` — conversion du code en arbre syntaxique
2. `NodeVisitor` — collecte des noms protégés (imports, builtins, dunders…)
3. `NodeTransformer` — modification de l'arbre (renommage, suppression, insertion)
4. `ast.unparse()` — regénération du code à partir de l'arbre modifié

Chaque transformation possède son propre `NodeTransformer` et elles s'enchaînent en pipeline. Le renommage fonctionne en deux passes : d'abord la collecte des noms à protéger, puis la transformation à proprement parler.

### Noms protégés

Les éléments suivants ne sont jamais renommés :

- Builtins (`print`, `len`, `range`…)
- Imports et modules
- Noms dunder (`__init__`, `__name__`…)
- Méthodes de classe
- Décorateurs
- `self` et `cls`

## Limites connues

- Il s'agit d'obfuscation, pas de chiffrement — un analyste suffisamment motivé peut toujours comprendre la logique.
- Les chaînes de caractères ne sont pas obfusquées.
- Les appels dynamiques (`getattr`, `eval`) ne sont pas pris en charge.
- Le renommage de fonctions ne s'applique pas aux méthodes de classe.

## Licence

MIT — voir [LICENSE](LICENSE).