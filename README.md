# Σύστημα Διαχείρισης Δημοτικής Αστυνομίας

Ένα ολοκληρωμένο σύστημα διαχείρισης παραβάσεων και προσωπικού για τη Δημοτική Αστυνομία.

## Χαρακτηριστικά

- 🔐 **Σύστημα Ρόλων**: Admin, PowerUser, User
- 📊 **Διαχείριση Παραβάσεων**: Καταχώρηση, επεξεργασία, προβολή
- 💬 **Σύστημα Μηνυμάτων**: Εσωτερική επικοινωνία
- 📈 **Αναφορές**: Στατιστικά και εκθέσεις
- 🎯 **Κεντρικό Dashboard**: Εύκολη πλοήγηση
- 🔄 **Web-based Migration**: Αναβάθμιση βάσης δεδομένων μέσω web interface

## Εγκατάσταση

Δείτε τις λεπτομερείς οδηγίες στο αρχείο `INSTALLATION_GUIDE_v3.md`.

## Deployment

Το σύστημα είναι έτοιμο για deployment σε:
- Railway
- Heroku
- Οποιαδήποτε πλατφόρμα που υποστηρίζει Flask

## Τεχνολογίες

- **Backend**: Flask, SQLAlchemy
- **Frontend**: HTML5, Bootstrap, JavaScript
- **Database**: SQLite
- **Authentication**: Flask-Login

## Δομή Αρχείων

```
/
├── app.py                    # Κύρια εφαρμογή
├── requirements.txt          # Dependencies
├── Procfile                  # Railway/Heroku config
├── INSTALLATION_GUIDE_v3.md  # Οδηγίες εγκατάστασης
├── templates/                # HTML templates
├── static/                   # CSS, JS, εικόνες
└── instance/                 # Βάση δεδομένων
```

## Άδεια

Αυτό το project είναι για εσωτερική χρήση της Δημοτικής Αστυνομίας.