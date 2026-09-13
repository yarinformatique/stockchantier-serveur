# 🌐 GUIDE DE DÉPLOIEMENT CLOUD 24H/24 — STOCKCHANTIER PRO

**Éditeur : YAR INFORMATIQUE — M. YAGO**  
**Siège : Ouagadougou (Burkina Faso) • Tél : 64 58 22 02 / 67 93 05 50**

Ce guide vous explique comment héberger votre Serveur de Synchronisation sur Internet afin qu'il fonctionne **24h/24 et 7j/7**, même lorsque votre ordinateur personnel est éteint.

---

## OPTION 1 : DÉPLOIEMENT GRATUIT SUR RENDER.COM (Recommandé - En 3 minutes)

**Render.com** permet d'héberger des applications web Python gratuitement, avec une adresse web sécurisée en `https://` (certificat SSL inclus).

### Étapes à suivre :
1. **Créer un compte gratuit sur Render** :
   - Rendez-vous sur [https://render.com](https://render.com) et créez un compte gratuit (avec votre adresse email ou GitHub).

2. **Créer un Web Service** :
   - Cliquez sur le bouton **« New + »** puis choisissez **« Web Service »**.
   - Vous pouvez soit lier votre dépôt GitHub contenant le dossier `DEPLOIEMENT_SERVEUR_CLOUD`, soit glisser les fichiers.
   - Configurez comme suit :
     - **Name** : `stockchantier-serveur`
     - **Region** : `Frankfurt (EU Central)` (proche de l'Afrique de l'Ouest)
     - **Language** : `Python 3`
     - **Build Command** : *(laisser vide)*
     - **Start Command** : `python saas_server.py`
     - **Plan** : `Free` (0 $/mois)
   - Cliquez sur **« Create Web Service »**.

3. **Récupérer l'URL de votre serveur Cloud** :
   - Render va générer une adresse permanente du genre :  
     `https://stockchantier-serveur.onrender.com`
   - Testez l'adresse dans votre navigateur : vous verrez la réponse du serveur et l'accès à votre console Super-Admin sur :  
     `https://stockchantier-serveur.onrender.com/superadmin_portal.html`

4. **Connecter vos clients à cette URL Cloud** :
   - Dans le logiciel client (ou lors de la configuration du Pass Entreprise), indiquez simplement cette adresse :  
     `https://stockchantier-serveur.onrender.com`
   - C'est tout ! Tous vos clients (PDG, Magasiniers, Chefs de chantier) se synchronisent désormais via le Cloud 24h/24 sans dépendre de votre PC.

---

## OPTION 2 : DÉPLOIEMENT SUR UN VPS (Serveur Privé Virtuel chez OVH, Hostinger, etc.)

Si vous disposez d'un VPS Linux (Ubuntu / Debian) :
1. Copiez les fichiers du dossier `DEPLOIEMENT_SERVEUR_CLOUD` sur le serveur :
   ```bash
   scp -r DEPLOIEMENT_SERVEUR_CLOUD/* root@votre-ip:/opt/stockchantier/
   ```
2. Lancez le serveur en arrière-plan avec `systemd` ou `screen` :
   ```bash
   cd /opt/stockchantier
   nohup python3 saas_server.py > server.log 2>&1 &
   ```
3. L'adresse de synchronisation de vos clients sera :
   `http://votre-ip-serveur:9000`

---

## VOTRE CONSOLE SUPER-ADMIN DEPUIS N'IMPORTE OÙ

Une fois le serveur en ligne :
- Ouvrez n'importe quel navigateur (sur votre smartphone ou votre PC) :  
  `https://votre-url-cloud/superadmin_portal.html`
- Connectez-vous avec vos identifiants :  
  **Identifiant** : `Abdoul Yago`  
  **Code** : `1762`
- Vous pilotez toutes vos entreprises clientes, leurs licences et leurs synchronisations en temps réel.
