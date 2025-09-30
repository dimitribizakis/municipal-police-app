#!/usr/bin/env python3
"""
Migration Script για την ενημέρωση των πεδίων οδηγού
Κάνει τα driver fields nullable στη βάση δεδομένων PostgreSQL
"""

import os
import psycopg2
from urllib.parse import urlparse

def run_migration():
    """Εκτελεί το migration για τα driver fields"""
    
    # Παίρνουμε το DATABASE_URL από το environment
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("❌ Δεν βρέθηκε DATABASE_URL στο environment")
        print("Βεβαιωθείτε ότι είστε συνδεδεμένοι στο Railway")
        return False
    
    # Parse το URL
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    try:
        # Σύνδεση στη βάση δεδομένων
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("🔗 Συνδέθηκα στη βάση δεδομένων...")
        
        # SQL commands για να κάνουμε τα driver fields nullable
        migration_commands = [
            "ALTER TABLE violation ALTER COLUMN driver_last_name DROP NOT NULL;",
            "ALTER TABLE violation ALTER COLUMN driver_first_name DROP NOT NULL;", 
            "ALTER TABLE violation ALTER COLUMN driver_father_name DROP NOT NULL;",
            "ALTER TABLE violation ALTER COLUMN driver_afm DROP NOT NULL;",
            "ALTER TABLE violation ALTER COLUMN driver_signature DROP NOT NULL;"
        ]
        
        print("📝 Εκτελώ migration commands...")
        
        for i, command in enumerate(migration_commands, 1):
            try:
                cursor.execute(command)
                field_name = command.split("ALTER COLUMN ")[1].split(" DROP")[0]
                print(f"✅ ({i}/5) {field_name} έγινε nullable")
            except psycopg2.errors.InvalidTableDefinition as e:
                if "does not exist" in str(e):
                    print(f"⚠️  Το πεδίο ήταν ήδη nullable ή δεν υπάρχει")
                else:
                    print(f"❌ Σφάλμα: {e}")
                    return False
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                return False
        
        # Commit τις αλλαγές
        conn.commit()
        print("\n🎉 Migration ολοκληρώθηκε επιτυχώς!")
        print("Τώρα τα στοιχεία οδηγού είναι προαιρετικά στη βάση δεδομένων.")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Σφάλμα σύνδεσης στη βάση: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Σύνδεση με βάση κλείστηκε")

if __name__ == "__main__":
    print("🚀 Ξεκινάω migration για driver fields...")
    print("=" * 50)
    
    success = run_migration()
    
    print("=" * 50)
    if success:
        print("✅ Migration ΕΠΙΤΥΧΗΜΕΝΟ!")
        print("\n📋 Επόμενα βήματα:")
        print("1. Restart την εφαρμογή στο Railway")
        print("2. Δοκιμάστε να καταχωρήσετε παράβαση χωρίς οδηγό")
    else:
        print("❌ Migration ΑΠΟΤΥΧΗΜΕΝΟ!")
        print("Παρακαλώ ελέγξτε τα σφάλματα πιο πάνω")