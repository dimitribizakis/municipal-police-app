# Οδηγός Deployment στο Railway.app

## Βήμα 1: Ετοιμασία Αρχείων (✅ Έτοιμα!)

Έχουν ήδη δημιουργηθεί τα απαραίτητα αρχεία:
- `requirements.txt` - Dependencies της Python
- `Procfile` - Εντολή για να τρέξει ο server
- `railway.json` - Ρυθμίσεις Railway
- `app.py` - Ανανεωμένο για production

## Βήμα 2: Δημιουργία GitHub Repository

1. Πήγαινε στο [GitHub.com](https://github.com)
2. Κάνε login ή δημιούργησε λογαριασμό
3. Κλικ "New Repository" (πράσινο κουμπί)
4. Όνομα repository: `municipal-police-app`
5. Κάνε το Public
6. Κλικ "Create Repository"

## Βήμα 3: Upload Αρχείων στο GitHub

**Μέθοδος 1 - Μέσω Web Interface:**
1. Στο νέο repository, κλικ "uploading an existing file"
2. Ανέβασε ΟΛΑ τα αρχεία από το project:
   - `app.py`
   - `requirements.txt`
   - `Procfile`
   - `railway.json`
   - `violations.json`
   - Φάκελο `templates/` (όλα τα HTML αρχεία)
   - Φάκελο `static/` (CSS, JS, logo.jpg)

**Μέθοδος 2 - Μέσω Git (αν έχεις εγκατεστημένο):**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/municipal-police-app.git
git push -u origin main
```

## Βήμα 4: Deployment στο Railway

1. **Πήγαινε στο [Railway.app](https://railway.app)**
2. **Κλικ "Start a New Project"**
3. **Επίλεξε "Deploy from GitHub repo"**
4. **Login με GitHub** (θα σου ζητήσει permission)
5. **Επίλεξε το repository** `municipal-police-app`
6. **Railway θα αρχίσει αυτόματα το deployment!**

## Βήμα 5: Παρακολούθηση Deployment

1. Θα δεις logs στη Railway console
2. Περίμενε μέχρι να λάβεις "Deployment Success" ✅
3. Κλικ στο URL που θα σου δώσει (π.χ. `your-app.railway.app`)

## Βήμα 6: Δοκιμή

1. Άνοιξε το URL της εφαρμογής
2. Δοκίμασε να καταχωρήσεις μια παράβαση
3. Ελέγξε αν όλα λειτουργούν σωστά

## Troubleshooting

**Αν δεν τρέχει:**
1. Ελέγξε τα logs στο Railway dashboard
2. Βεβαιώσου ότι όλα τα αρχεία ανέβηκαν στο GitHub
3. Ελέγξε ότι το `requirements.txt` έχει τις σωστές εκδόσεις

**Domain Name (προαιρετικό):**
- Στο Railway μπορείς να βάλεις custom domain
- Ή χρησιμοποίησε το default railway.app subdomain

## Κόστος
- Railway έχει δωρεάν tier με περιορισμούς
- Για production χρήση, μικρό μηνιαίο κόστος (~$5)

---
*Εφαρμογή Δημοτικής Αστυνομίας - Παραβάσεις Οχημάτων*