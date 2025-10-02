#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration Script: Προσθήκη στήλης related_message_id στον πίνακα notification
Ημερομηνία: 02/10/2025
Περιγραφή: Προσθήκη στήλης για σύνδεση ειδοποιήσεων με μηνύματα
"""

import sqlite3
import os
import sys
from datetime import datetime

# Διαδρομή της βάσης δεδομένων
DB_PATH = 'instance/municipal_police_v3.db'

def backup_database():
    """Δημιουργία αντιγράφου ασφαλείας της βάσης δεδομένων"""
    if os.path.exists(DB_PATH):
        backup_name = f"instance/municipal_police_v3_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        import shutil
        shutil.copy2(DB_PATH, backup_name)
        print(f"✅ Αντίγραφο ασφαλείας δημιουργήθηκε: {backup_name}")
        return backup_name
    else:
        print(f"❌ Η βάση δεδομένων δεν βρέθηκε στη διαδρομή: {DB_PATH}")
        return None

def check_column_exists(cursor, table_name, column_name):
    """Έλεγχος αν υπάρχει η στήλη στον πίνακα"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    return column_name in column_names

def add_related_message_id_column():
    """Προσθήκη της στήλης related_message_id στον πίνακα notification"""
    
    try:
        # Δημιουργία αντιγράφου ασφαλείας
        backup_file = backup_database()
        if not backup_file:
            return False
            
        # Σύνδεση με τη βάση δεδομένων
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Έλεγχος αν υπάρχει ήδη η στήλη
        if check_column_exists(cursor, 'notification', 'related_message_id'):
            print("✅ Η στήλη 'related_message_id' υπάρχει ήδη στον πίνακα 'notification'")
            conn.close()
            return True
            
        print("🔄 Προσθήκη στήλης 'related_message_id' στον πίνακα 'notification'...")
        
        # Προσθήκη της νέας στήλης
        cursor.execute("""
            ALTER TABLE notification 
            ADD COLUMN related_message_id INTEGER
        """)
        
        print("✅ Η στήλη 'related_message_id' προστέθηκε επιτυχώς!")
        
        # Έλεγχος αν υπάρχει ο πίνακας message για το foreign key
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message'")
        if cursor.fetchone():
            print("📋 Ο πίνακας 'message' βρέθηκε - το foreign key constraint θα δημιουργηθεί αυτόματα από τη SQLAlchemy")
        else:
            print("⚠️  Ο πίνακας 'message' δεν βρέθηκε - θα πρέπει να δημιουργηθεί πρώτα")
        
        # Commit των αλλαγών
        conn.commit()
        
        # Έλεγχος της νέας δομής
        print("\n📊 Νέα δομή πίνακα 'notification':")
        cursor.execute("PRAGMA table_info(notification)")
        columns = cursor.fetchall()
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
            
        conn.close()
        print(f"\n✅ Migration ολοκληρώθηκε επιτυχώς!")
        print(f"📁 Αντίγραφο ασφαλείας: {backup_file}")
        return True
        
    except Exception as e:
        print(f"❌ Σφάλμα κατά το migration: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def main():
    """Κύρια function"""
    print("🚀 Έναρξη Database Migration")
    print("=" * 50)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Η βάση δεδομένων δεν βρέθηκε στη διαδρομή: {DB_PATH}")
        print("💡 Βεβαιωθείτε ότι βρίσκεστε στο root directory της εφαρμογής")
        return False
    
    success = add_related_message_id_column()
    
    if success:
        print("\n🎉 Migration ολοκληρώθηκε με επιτυχία!")
        print("📋 Τώρα μπορείτε να επανεκκινήσετε την εφαρμογή σας")
    else:
        print("\n💥 Migration απέτυχε!")
        print("🔧 Παρακαλώ ελέγξτε τα σφάλματα παραπάνω")
    
    return success

if __name__ == "__main__":
    main()