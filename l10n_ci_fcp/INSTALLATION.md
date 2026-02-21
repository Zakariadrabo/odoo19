# Guide d'Installation - Module l10n_ci_fcp

## Table des matières
1. [Prérequis](#prérequis)
2. [Installation du module](#installation-du-module)
3. [Configuration initiale](#configuration-initiale)
4. [Vérification](#vérification)
5. [Dépannage](#dépannage)

---

## Prérequis

### Système
- **Odoo version** : 19.0 ou supérieur
- **Base de données** : PostgreSQL 12+
- **Python** : 3.10+

### Modules Odoo
- `account` (module de comptabilité - installé par défaut)

---

## Installation du module

### Méthode 1 : Installation manuelle

1. **Copier le module dans le dossier addons**
   ```bash
   # Localiser votre dossier addons Odoo
   cd /opt/odoo/addons  # ou /path/to/odoo/addons
   
   # Copier le module
   cp -r /path/to/l10n_ci_fcp .
   
   # Vérifier les permissions
   chown -R odoo:odoo l10n_ci_fcp
   chmod -R 755 l10n_ci_fcp
   ```

2. **Ajouter le chemin dans la configuration Odoo** (si nécessaire)
   
   Éditer `/etc/odoo/odoo.conf` :
   ```ini
   [options]
   addons_path = /opt/odoo/addons,/path/to/custom/addons
   ```

3. **Redémarrer le serveur Odoo**
   ```bash
   sudo systemctl restart odoo
   # ou pour un serveur de développement
   ./odoo-bin -c odoo.conf --update=all
   ```

### Méthode 2 : Installation via interface Odoo

1. **Activer le mode développeur**
   - Aller dans `Paramètres` → `Activer le mode développeur`

2. **Mettre à jour la liste des applications**
   - Aller dans `Apps`
   - Cliquer sur `Update Apps List`
   - Confirmer

3. **Rechercher et installer le module**
   - Dans `Apps`, rechercher "Côte d'Ivoire FCP" ou "l10n_ci_fcp"
   - Cliquer sur `Install`

---

## Configuration initiale

### 1. Configuration de la société

Après installation, configurez votre société :

```
Comptabilité → Configuration → Paramètres → Comptabilité
```

**Paramètres à configurer :**
- **Pays** : Côte d'Ivoire (CI)
- **Devise** : XOF - Franc CFA (BCEAO)
- **Plan comptable** : Plan Comptable FCP - Côte d'Ivoire
- **Périodes fiscales** : Janvier-Décembre

### 2. Vérification du plan comptable

```
Comptabilité → Configuration → Comptabilité → Plan Comptable
```

Vous devriez voir :
- 108 comptes créés
- Comptes groupés par classes (1-9)
- Types de comptes correctement assignés

### 3. Vérification des journaux

```
Comptabilité → Configuration → Comptabilité → Journaux
```

Journaux créés :
- ✓ SOUS - Souscriptions
- ✓ RACH - Rachats
- ✓ VALO - Valorisation des Titres
- ✓ TITR - Opérations sur Titres
- ✓ REVE - Revenus de Titres
- ✓ DIVI - Dividendes
- ✓ FRAIS - Frais de Gestion
- ✓ BNQ - Banque
- ✓ CSE - Caisse
- ✓ OD - Opérations Diverses
- ✓ REGUL - Régularisations
- ✓ CREP - CREPMF/BRVM

### 4. Vérification des taxes

```
Comptabilité → Configuration → Comptabilité → Taxes
```

Taxes créées :
- ✓ TVA 18% Achat
- ✓ TVA 18% Vente
- ✓ TVA 18% Commission
- ✓ TVA 18% Service
- ✓ TOB 0.3%
- ✓ Impôt sur Bénéfices

### 5. Configuration des comptes bancaires

```
Comptabilité → Configuration → Comptabilité → Banques
```

Ajoutez vos comptes bancaires :
- **Compte BOA-CI** : Utiliser le compte 121001
- **Autres banques** : Créer des sous-comptes si nécessaire

---

## Vérification

### Test 1 : Créer une écriture de souscription

1. Aller dans `Comptabilité → Comptabilité → Écritures`
2. Créer une nouvelle écriture
3. Journal : `SOUS - Souscriptions`
4. Ajouter les lignes :
   - Débit : 121001 (Compte Courant) - 1,000,000 XOF
   - Crédit : 572100 (Souscriptions exercice) - 1,000,000 XOF
5. Valider l'écriture

✅ Si l'écriture est validée sans erreur, le module fonctionne correctement.

### Test 2 : Vérifier la balance

```
Comptabilité → Rapports → Balance
```

Vérifiez que :
- Les comptes s'affichent correctement
- Les groupes sont bien structurés
- Les totaux sont équilibrés

---

## Dépannage

### Problème : Le module n'apparaît pas dans la liste

**Solution :**
1. Vérifier que le module est dans le bon dossier addons
2. Vérifier les permissions du dossier
3. Redémarrer Odoo avec :
   ```bash
   ./odoo-bin -c odoo.conf --update=all
   ```
4. Mettre à jour la liste des apps

### Problème : Erreur lors de l'installation

**Erreur commune : "Module l10n_ci_fcp not found"**

**Solution :**
1. Vérifier que `__manifest__.py` existe
2. Vérifier la syntaxe du manifest
3. Consulter les logs :
   ```bash
   tail -f /var/log/odoo/odoo.log
   ```

### Problème : Les comptes ne s'affichent pas

**Solution :**
1. Vérifier que le fichier CSV est bien chargé
2. Vérifier le format du CSV (encodage UTF-8)
3. Réinstaller le module :
   ```
   Apps → l10n_ci_fcp → Désinstaller → Réinstaller
   ```

### Problème : Les taxes ne fonctionnent pas

**Solution :**
1. Vérifier la configuration dans `account_tax_template_data.xml`
2. Vérifier que les comptes de TVA existent
3. Recréer les taxes manuellement si nécessaire

---

## Commandes utiles

### Redémarrer Odoo (production)
```bash
sudo systemctl restart odoo
sudo systemctl status odoo
```

### Redémarrer Odoo (développement)
```bash
./odoo-bin -c odoo.conf -d your_database --update=l10n_ci_fcp
```

### Vérifier les logs
```bash
tail -f /var/log/odoo/odoo.log
```

### Mettre à jour uniquement ce module
```bash
./odoo-bin -c odoo.conf -d your_database -u l10n_ci_fcp
```

---

## Support

Pour toute assistance :
- 📧 Email : support@votreentreprise.ci
- 📖 Documentation Odoo : https://www.odoo.com/documentation/19.0/

---

## Notes importantes

⚠️ **Sauvegarde** : Toujours faire une sauvegarde de votre base de données avant d'installer un nouveau module.

⚠️ **Test** : Testez d'abord sur un environnement de développement avant de déployer en production.

⚠️ **Mise à jour** : Ce module est conçu pour Odoo 19. Vérifiez la compatibilité avant de mettre à jour Odoo.
