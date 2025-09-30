#!/usr/bin/env python3
"""
Migration Script: Προσθήκη πεδίων προστίμων στις παραβάσεις

Αυτό το script προσθέτει τα νέα πεδία για τα ποσά παραβάσεων και άρθρα
και ενημερώνει όλες τις υπάρχουσες παραβάσεις.

Νέα πεδία:
- violation_articles: JSON με άρθρα παραβάσεων  
- total_fine_amount: Συνολικό ποσό προστίμου
- fine_breakdown: JSON με αναλυτικά πρόστιμα

Χρήση: python migrate_violation_fines.py
"""

import os
import sys
import json
from datetime import datetime

# Προσθήκη του workspace path για import του app
sys.path.insert(0, '/workspace')

from app import app, db, Violation, load_violations

def add_new_columns():
    """Προσθήκη νέων στηλών στη βάση δεδομένων"""
    print("Προσθήκη νέων στηλών στη βάση δεδομένων...")
    
    with app.app_context():
        try:
            # Για SQLite (development) - χρήση ALTER TABLE
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN violation_articles TEXT"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN total_fine_amount NUMERIC(8,2)"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN fine_breakdown TEXT"))
                print("✓ Στήλες προστέθηκαν επιτυχώς (SQLite)")
            else:
                # Για PostgreSQL (production)
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS violation_articles TEXT"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS total_fine_amount NUMERIC(8,2)"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS fine_breakdown TEXT"))
                print("✓ Στήλες προστέθηκαν επιτυχώς (PostgreSQL)")
                
            db.session.commit()
            
        except Exception as e:
            print(f"⚠️  Πιθανώς οι στήλες υπάρχουν ήδη ή υπήρξε σφάλμα: {e}")
            # Συνεχίζουμε γιατί μπορεί οι στήλες να υπάρχουν ήδη
            db.session.rollback()

def update_existing_violations():
    """Ενημέρωση υπαρχουσών παραβάσεων με τα ποσά προστίμων"""
    print("Ενημέρωση υπαρχουσών παραβάσεων...")
    
    with app.app_context():
        # Φόρτωση δεδομένων παραβάσεων
        violations_data = load_violations()
        print(f"Φορτώθηκαν {len(violations_data)} παραβάσεις από violations.json")
        
        # Λήψη όλων των παραβάσεων που δεν έχουν ποσό
        violations = Violation.query.filter(
            (Violation.total_fine_amount == None) | 
            (Violation.total_fine_amount == 0)
        ).all()
        
        print(f"Βρέθηκαν {len(violations)} παραβάσεις για ενημέρωση")
        
        updated_count = 0
        for violation in violations:
            try:
                # Υπολογισμός προστίμου
                total_fine = violation.calculate_total_fine(violations_data, violation.vehicle_type)
                
                if total_fine > 0:
                    updated_count += 1
                    print(f"Ενημερώθηκε παράβαση #{violation.id}: {total_fine}€ για {violation.vehicle_type}")
                
            except Exception as e:
                print(f"⚠️  Σφάλμα στην ενημέρωση παράβασης #{violation.id}: {e}")
                continue
        
        # Bulk commit για καλύτερη απόδοση
        try:
            db.session.commit()
            print(f"✓ Ενημερώθηκαν επιτυχώς {updated_count} παραβάσεις")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Σφάλμα κατά την αποθήκευση: {e}")
            return False
    
    return True

def verify_migration():
    """Επαλήθευση ότι το migration ολοκληρώθηκε επιτυχώς"""
    print("Επαλήθευση migration...")
    
    with app.app_context():
        # Έλεγχος ότι υπάρχουν οι νέες στήλες
        try:
            sample_violation = Violation.query.first()
            if sample_violation:
                # Προσπάθεια πρόσβασης στα νέα πεδία
                _ = sample_violation.total_fine_amount
                _ = sample_violation.violation_articles
                _ = sample_violation.fine_breakdown
                print("✓ Νέα πεδία προσβάσιμα")
            else:
                print("ℹ️  Δεν υπάρχουν παραβάσεις στη βάση για δοκιμή")
            
            # Στατιστικά
            total_violations = Violation.query.count()
            violations_with_fines = Violation.query.filter(Violation.total_fine_amount > 0).count()
            
            print(f"📊 Στατιστικά:")
            print(f"   - Συνολικές παραβάσεις: {total_violations}")
            print(f"   - Παραβάσεις με ποσά: {violations_with_fines}")
            
            if total_violations > 0:
                percentage = (violations_with_fines/total_violations)*100
                print(f"   - Ποσοστό ολοκλήρωσης: {percentage:.1f}%")
            else:
                print("   - Ποσοστό ολοκλήρωσης: Δεν εφαρμόζεται (κενή βάση)")
            
            return True
            
        except Exception as e:
            print(f"❌ Σφάλμα στην επαλήθευση: {e}")
            return False

def main():
    """Κύρια συνάρτηση migration"""
    print("🚀 Έναρξη Migration: Προσθήκη πεδίων προστίμων παραβάσεων")
    print("=" * 60)
    
    # Βήμα 1: Προσθήκη νέων στηλών
    add_new_columns()
    
    # Βήμα 2: Ενημέρωση υπαρχουσών δεδομένων
    if update_existing_violations():
        print("✓ Ενημέρωση δεδομένων ολοκληρώθηκε")
    else:
        print("❌ Σφάλμα στην ενημέρωση δεδομένων")
        return False
    
    # Βήμα 3: Επαλήθευση
    if verify_migration():
        print("✓ Migration ολοκληρώθηκε επιτυχώς!")
        return True
    else:
        print("❌ Migration απέτυχε!")
        return False

if __name__ == "__main__":
    if main():
        print("\n🎉 Migration ολοκληρώθηκε επιτυχώς!")
        print("Τώρα όλες οι παραβάσεις περιλαμβάνουν άρθρα και ποσά προστίμων.")
    else:
        print("\n💥 Migration απέτυχε!")
        print("Παρακαλώ ελέγξτε τα σφάλματα και δοκιμάστε ξανά.")
        sys.exit(1)