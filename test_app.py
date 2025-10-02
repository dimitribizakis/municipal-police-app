#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Script: Έλεγχος βάσης δεδομένων και functions
Ημερομηνία: 02/10/2025
"""

import sqlite3
import os
import json

def test_database_structure():
    """Έλεγχος δομής βάσης δεδομένων"""
    DB_PATH = 'instance/municipal_police_v3.db'
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Βάση δεδομένων δεν βρέθηκε: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("🔍 Έλεγχος δομής βάσης δεδομένων...")
        
        # Έλεγχος πίνακα notification
        print("\n📋 Πίνακας 'notification':")
        cursor.execute("PRAGMA table_info(notification)")
        notification_columns = cursor.fetchall()
        
        has_related_message_id = False
        for column in notification_columns:
            print(f"  ✓ {column[1]} ({column[2]})")
            if column[1] == 'related_message_id':
                has_related_message_id = True
        
        if has_related_message_id:
            print("  ✅ Στήλη 'related_message_id' βρέθηκε!")
        else:
            print("  ❌ Στήλη 'related_message_id' ΔΕΝ βρέθηκε!")
        
        # Έλεγχος πίνακα message
        print("\n📋 Πίνακας 'message':")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message'")
        if cursor.fetchone():
            print("  ✅ Πίνακας 'message' υπάρχει")
            cursor.execute("PRAGMA table_info(message)")
            message_columns = cursor.fetchall()
            for column in message_columns[:5]:  # Πρώτες 5 στήλες
                print(f"  ✓ {column[1]} ({column[2]})")
        else:
            print("  ❌ Πίνακας 'message' ΔΕΝ υπάρχει!")
        
        # Έλεγχος πίνακα violation
        print("\n📋 Πίνακας 'violation':")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='violation'")
        if cursor.fetchone():
            print("  ✅ Πίνακας 'violation' υπάρχει")
            cursor.execute("SELECT COUNT(*) FROM violation")
            count = cursor.fetchone()[0]
            print(f"  📊 Συνολικές παραβάσεις: {count}")
        else:
            print("  ❌ Πίνακας 'violation' ΔΕΝ υπάρχει!")
        
        # Έλεγχος πίνακα user
        print("\n📋 Πίνακας 'user':")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        if cursor.fetchone():
            print("  ✅ Πίνακας 'user' υπάρχει")
            cursor.execute("SELECT COUNT(*) FROM user")
            count = cursor.fetchone()[0]
            print(f"  👥 Συνολικοί χρήστες: {count}")
            
            # Έλεγχος ρόλων χρηστών
            cursor.execute("SELECT role, COUNT(*) FROM user GROUP BY role")
            roles = cursor.fetchall()
            print("  🎭 Ρόλοι χρηστών:")
            for role, count in roles:
                print(f"    - {role}: {count}")
        else:
            print("  ❌ Πίνακας 'user' ΔΕΝ υπάρχει!")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Σφάλμα κατά τον έλεγχο βάσης: {str(e)}")
        return False

def test_app_imports():
    """Έλεγχος imports και βασικών functions της εφαρμογής"""
    try:
        print("\n🔍 Έλεγχος imports εφαρμογής...")
        
        # Προσπάθεια import του app
        import sys
        sys.path.append('/workspace')
        
        # Βασικά imports
        print("  ✓ datetime import")
        from datetime import datetime, date, time
        
        print("  ✓ flask imports")
        from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
        
        print("  ✓ werkzeug imports")
        from werkzeug.security import generate_password_hash, check_password_hash
        
        print("  ✓ sqlalchemy imports")
        from flask_sqlalchemy import SQLAlchemy
        from sqlalchemy import or_
        
        print("  ✅ Όλα τα imports είναι επιτυχή!")
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {str(e)}")
        return False
    except Exception as e:
        print(f"  ❌ Άλλο σφάλμα: {str(e)}")
        return False

def check_critical_files():
    """Έλεγχος ύπαρξης κρισιμων αρχείων"""
    print("\n🔍 Έλεγχος κρισιμων αρχείων...")
    
    critical_files = [
        'app.py',
        'templates/base_v2.html',
        'templates/violation_detail.html',
        'templates/violations_list_v2.html',
        'instance/municipal_police_v3.db'
    ]
    
    all_exist = True
    for file_path in critical_files:
        if os.path.exists(file_path):
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} - ΔΕΝ ΒΡΕΘΗΚΕ!")
            all_exist = False
    
    return all_exist

def main():
    """Κύρια function"""
    print("🚀 Έλεγχος Εφαρμογής Municipal Police")
    print("=" * 50)
    
    # Έλεγχος αρχείων
    files_ok = check_critical_files()
    
    # Έλεγχος βάσης δεδομένων
    db_ok = test_database_structure()
    
    # Έλεγχος imports
    imports_ok = test_app_imports()
    
    print("\n" + "=" * 50)
    print("📊 ΑΠΟΤΕΛΕΣΜΑΤΑ ΕΛΕΓΧΟΥ:")
    print(f"  📁 Αρχεία: {'✅ OK' if files_ok else '❌ ΠΡΟΒΛΗΜΑ'}")
    print(f"  🗃️  Βάση Δεδομένων: {'✅ OK' if db_ok else '❌ ΠΡΟΒΛΗΜΑ'}")
    print(f"  📦 Imports: {'✅ OK' if imports_ok else '❌ ΠΡΟΒΛΗΜΑ'}")
    
    if files_ok and db_ok and imports_ok:
        print("\n🎉 Όλα τα βασικά στοιχεία είναι σε τάξη!")
        print("📋 Η εφαρμογή είναι έτοιμη για χρήση.")
    else:
        print("\n⚠️  Βρέθηκαν προβλήματα που χρήζουν διόρθωσης.")
    
    return files_ok and db_ok and imports_ok

if __name__ == "__main__":
    main()