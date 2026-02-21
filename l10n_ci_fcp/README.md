# Module de Localisation Comptable - Côte d'Ivoire (FCP)

## Description

Module de localisation pour Odoo 19 adapté aux **Fonds Communs de Placement (FCP)** en Côte d'Ivoire.

Ce module fournit :
- ✅ Plan comptable complet adapté aux FCP
- ✅ Journaux comptables spécifiques (souscriptions, rachats, valorisation, etc.)
- ✅ Taxes et régimes fiscaux ivoiriens (TVA 18%, TOB, etc.)
- ✅ Configuration automatique lors de l'installation
- ✅ Conforme au SYSCOHADA et réglementations CREPMF/BRVM

## Installation

### Prérequis
- Odoo 19
- Module `account` (installé par défaut)

### Étapes d'installation

1. **Copier le module dans le dossier addons**
   ```bash
   cp -r l10n_ci_fcp /path/to/odoo/addons/
   ```

2. **Redémarrer le serveur Odoo**
   ```bash
   sudo systemctl restart odoo
   # ou
   ./odoo-bin --update=all
   ```

3. **Mettre à jour la liste des applications**
   - Aller dans `Apps` → `Update Apps List`

4. **Installer le module**
   - Rechercher "Côte d'Ivoire - Comptabilité FCP"
   - Cliquer sur `Install`

## Configuration

### Configuration automatique

Lors de l'installation, le module configure automatiquement :
- Plan comptable complet (108 comptes)
- 12 journaux comptables
- 6 taxes (TVA 18%, TOB, etc.)
- Groupes de comptes

### Configuration manuelle (optionnelle)

#### 1. Configurer la société
```
Comptabilité → Configuration → Paramètres
```
- **Pays** : Côte d'Ivoire
- **Devise** : XOF (Franc CFA)
- **Plan comptable** : Plan Comptable FCP - Côte d'Ivoire

#### 2. Vérifier les comptes par défaut
```
Comptabilité → Configuration → Comptabilité → Plan Comptable
```

Les comptes suivants sont configurés par défaut :
- **Clients** : 371200 - Clients, compte espèces
- **Fournisseurs** : 389904 - Créditeurs divers
- **Achats** : 603100 - Frais de gestion
- **Ventes** : 710100 - Revenus des ACTIONS

## Structure du Plan Comptable

### Classe 1 - Comptes de Trésorerie
- **111001** : Compte Espèces
- **121001** : Compte Courant
- **141xxx** : Intérêts courus

### Classe 2 - Comptes d'Actif
- **217xxx** : Différences d'estimation (Actions, Obligations, OPCVM)
- **240xxx** : Titres à recevoir (Obligations, Bons, Actions, OPCVM)

### Classe 3 - Comptes de Tiers et TVA
- **35xxxx** : TVA et Impôts
- **371200** : Clients
- **389xxx** : Comptes de tiers (Conservateurs, CREPMF, Dividendes, etc.)

### Classe 5 - Capitaux Propres FCP
- **551xxx** : Plus/Moins-values sur titres
- **553xxx** : Différences d'estimation et droits
- **571xxx** : Capital et régularisations
- **572xxx** : Souscriptions et rachats
- **58xxxx** : Reports à nouveau
- **591xxx** : Résultats

### Classe 6 - Comptes de Charges
- **603xxx** : Frais de gestion et droits de garde
- **615xxx** : Frais bancaires, honoraires, redevances
- **690000** : Impôt sur les bénéfices

### Classe 7 - Comptes de Produits
- **710xxx** : Revenus de titres (Actions, Obligations, OPCVM)
- **727xxx** : Intérêts courus
- **731100** : Revenus sur placements

### Classe 9 - Comptes Hors Bilan
- **922xxx** : Titres à recevoir du Dépositaire Central
- **94xxxx** : Souscriptions/Rachats
- **95xxxx** : Stock de titres (Obligations, Bons, Actions, OPCVM)
- **960001** : Stock de parts

## Journaux Comptables

Le module crée automatiquement 12 journaux :

| Code | Nom | Type | Usage |
|------|-----|------|-------|
| SOUS | Souscriptions | Général | Enregistrement des souscriptions |
| RACH | Rachats | Général | Enregistrement des rachats |
| VALO | Valorisation des Titres | Général | Valorisation quotidienne |
| TITR | Opérations sur Titres | Général | Achats/Ventes de titres |
| REVE | Revenus de Titres | Général | Dividendes, coupons |
| DIVI | Dividendes | Général | Distribution de dividendes |
| FRAIS | Frais de Gestion | Général | Frais SGO, garde, etc. |
| BNQ | Banque | Banque | Opérations bancaires |
| CSE | Caisse | Caisse | Opérations de caisse |
| OD | Opérations Diverses | Général | Autres opérations |
| REGUL | Régularisations | Général | Régularisations comptables |
| CREP | CREPMF/BRVM | Général | Redevances et frais CREPMF |

## Taxes

### TVA (18%)
- **TVA 18% Achat** : TVA récupérable sur achats
- **TVA 18% Vente** : TVA collectée sur prestations
- **TVA 18% Commission** : TVA sur commissions
- **TVA 18% Service** : TVA sur services extérieurs

### Autres Taxes
- **TOB 0.3%** : Taxe sur Opérations Boursières
- **Impôt sur Bénéfices** : Impôt sur les bénéfices

## Utilisation

### Exemple : Enregistrer une souscription

```
Journal : SOUS - Souscriptions
Débit  : 121001 - Compte Courant
Crédit : 572100 - Souscriptions exercice
```

### Exemple : Enregistrer un rachat

```
Journal : RACH - Rachats
Débit  : 572200 - Rachats exercice
Crédit : 121001 - Compte Courant
```

### Exemple : Valorisation des titres

```
Journal : VALO - Valorisation des Titres
Débit  : 217300 - Différence d'estimation ACTIONS
Crédit : 553100 - Différence d'estimation portefeuille
```

### Exemple : Revenus d'actions

```
Journal : REVE - Revenus de Titres
Débit  : 389007 - Revenus / Actions à encaisser
Crédit : 710100 - Revenus des ACTIONS
```

## Support et Contribution

Pour toute question ou suggestion d'amélioration :
- Email : support@votreentreprise.ci
- Documentation : https://www.odoo.com/documentation/19.0/

## Licence

LGPL-3

## Auteurs

- Votre Entreprise

## Changelog

### Version 19.0.1.0.0 (2026-02-12)
- Version initiale
- Plan comptable complet (108 comptes)
- 12 journaux comptables
- 6 taxes configurées
- Configuration automatique
