#!/usr/bin/env python3
"""
Migration Script: Επέκταση πίνακα ViolationsData
Προσθήκη νέων πεδίων για πλήρη διαχείριση παραβάσεων ΚΟΚ
"""

import sqlite3
import os
from datetime import datetime

def migrate_violations_data():
    """Επέκταση πίνακα violations_data με νέα πεδία"""
    
    db_path = 'instance/municipal_police_v3.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Η βάση δεδομένων {db_path} δεν υπάρχει!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Ξεκινάει η επέκταση του πίνακα violations_data...")
        
        # Έλεγχος αν υπάρχουν ήδη τα νέα πεδία
        cursor.execute("PRAGMA table_info(violations_data)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Λίστα νέων στηλών προς προσθήκη
        new_columns = [
            ("article", "VARCHAR(20)"),
            ("article_paragraph", "VARCHAR(20)"),
            ("half_fine_motorcycles", "BOOLEAN DEFAULT 0"),
            ("remove_circulation_elements", "BOOLEAN DEFAULT 0"),
            ("circulation_removal_days", "INTEGER"),
            ("remove_circulation_license", "BOOLEAN DEFAULT 0"),
            ("circulation_license_removal_days", "INTEGER"),
            ("remove_driving_license", "BOOLEAN DEFAULT 0"),
            ("driving_license_removal_days", "INTEGER"),
            ("parking_special_provision", "BOOLEAN DEFAULT 0"),
            ("updated_at", "DATETIME")
        ]
        
        # Προσθήκη νέων στηλών (μόνο αν δεν υπάρχουν)
        added_columns = []
        for column_name, column_type in new_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE violations_data ADD COLUMN {column_name} {column_type}")
                    added_columns.append(column_name)
                    print(f"✅ Προστέθηκε στήλη: {column_name}")
                except sqlite3.Error as e:
                    print(f"⚠️ Σφάλμα κατά την προσθήκη στήλης {column_name}: {e}")
        
        if added_columns:
            # Ενημέρωση updated_at για υπάρχουσες εγγραφές
            current_time = datetime.now().isoformat()
            cursor.execute("UPDATE violations_data SET updated_at = ? WHERE updated_at IS NULL", (current_time,))
            
            conn.commit()
            print(f"🎉 Επέκταση ολοκληρώθηκε! Προστέθηκαν {len(added_columns)} νέες στήλες.")
        else:
            print("ℹ️ Όλες οι στήλες υπάρχουν ήδη. Δεν χρειάζεται migration.")
        
        # Εμφάνιση τελικής δομής
        cursor.execute("PRAGMA table_info(violations_data)")
        final_columns = cursor.fetchall()
        print("\n📋 Τελική δομή πίνακα violations_data:")
        for col in final_columns:
            print(f"   {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Σφάλμα στη βάση δεδομένων: {e}")
        return False
    except Exception as e:
        print(f"❌ Απροσδόκητο σφάλμα: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Migration Script: Επέκταση ViolationsData")
    print("=" * 50)
    
    success = migrate_violations_data()
    
    print("=" * 50)
    if success:
        print("✅ Migration ολοκληρώθηκε επιτυχώς!")
    else:
        print("❌ Migration απέτυχε!")