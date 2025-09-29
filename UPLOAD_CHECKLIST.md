# 📋 ΛΙΣΤΑ ΑΡΧΕΙΩΝ ΓΙΑ UPLOAD ΣΤΟ GITHUB

## 🎯 **ΟΛΑ ΤΑ ΑΡΧΕΙΑ ΠΟΥ ΠΡΕΠΕΙ ΝΑ ΑΝΕΒΑΣΕΙΣ:**

### 📁 **Root Directory (κύρια αρχεία)**
```
✅ app_v2.py                    # Νέα κύρια εφαρμογή
✅ violations.json              # Παραβάσεις (υπάρχον)
✅ requirements.txt             # Ενημερωμένο με νέες dependencies
✅ Procfile                     # Production server config
✅ railway.json                 # Railway deployment settings
✅ V2_UPGRADE_GUIDE.md          # Οδηγός αναβάθμισης
✅ README.md                    # Ενημερωμένη τεκμηρίωση
```

### 📁 **templates/ Directory**
```
✅ base_v2.html                 # Νέο base template με auth
✅ login.html                   # Login page
✅ index_v2.html                # Νέα φόρμα με camera & dynamic fields
✅ violations_list_v2.html      # Ενημερωμένη λίστα παραβάσεων
✅ violation_detail.html        # Υπάρχον (keep existing)
```

### 📁 **templates/admin/ Directory**
```
✅ dashboard.html               # Admin dashboard
✅ users.html                   # User management
✅ add_user.html                # Add new user form
✅ violations.html              # Admin violations list
✅ edit_violation.html          # Edit violation form
✅ reports.html                 # Reports generator
✅ report_result.html           # Report display
```

### 📁 **static/ Directory**
```
✅ logo.jpg                     # Λογότυπο Δημοτικής Αστυνομίας (υπάρχον)
✅ uploads/                     # Φάκελος φωτογραφιών (άδειος)
```

---

## 🚀 **DEPLOYMENT STEPS:**

### **1. GitHub Repository**
```
1. Πήγαινε στο GitHub repository σου
2. Delete όλα τα παλιά αρχεία (εκτός από static/logo.jpg)
3. Upload όλα τα νέα αρχεία από τη λίστα παραπάνω
4. Commit changes: "v2.0 Full Rebuild - Camera + Admin + Auth"
```

### **2. Railway Redeploy**
```
1. Πήγαινε στο Railway dashboard
2. Railway θα detect αυτόματα τις αλλαγές
3. Θα ξεκινήσει automatic redeploy
4. Περίμενε να ολοκληρωθεί (2-3 λεπτά)
```

### **3. First Login**
```
🔑 Default Admin Credentials:
   Username: admin
   Password: admin123

⚠️  ΑΛΛΑΞΕ ΤΟΝ ΚΩΔΙΚΟ ΑΜΕΣΑ!
```

---

## 📱 **ΝΕΑ FEATURES ΠΟΥ ΘΑ ΔΕΙΣ:**

### **✅ Camera Support**
- Κλικ "Άνοιγμα Κάμερας" → Άμεση πρόσβαση στην κάμερα
- Φωτογράφισε το όχημα → Αυτόματη αποθήκευση

### **✅ Dynamic Fields**
- Χρώμα/Τύπος οχήματος → Επιλογή "Άλλο" → Νέα επιλογή αποθηκεύεται

### **✅ Admin Panel**
- Login ως admin → Διαχείριση menu → Πλήρης έλεγχος

### **✅ User Management**
- Προσθήκη νέων αστυνομικών
- Κάθε αστυνομικός έχει δικό του login

---

## ⚠️ **ΣΗΜΑΝΤΙΚΕΣ ΑΛΛΑΓΕΣ:**

### **🔄 Νέο Main File:**
- Το `app.py` αντικαθίσταται από `app_v2.py`
- Railway θα χρησιμοποιήσει αυτόματα το νέο αρχείο

### **🗄️ Νέα Database:**
- Θα δημιουργηθεί `municipal_police_v2.db`
- Παλιά δεδομένα θα χαθούν (αν θες backup, πες μου)

### **👥 Authentication Required:**
- Όλοι οι χρήστες πρέπει να κάνουν login
- Default admin: admin/admin123

---

## 🎯 **ΑΜΕΣΕΣ ΕΝΕΡΓΕΙΕΣ ΜΕΤΑ ΤΟ DEPLOY:**

1. **✅ Test Login**: Δοκίμασε admin/admin123
2. **🔒 Change Password**: Άλλαξε τον admin κωδικό
3. **👤 Add Officers**: Προσθες τους αστυνομικούς σου
4. **📸 Test Camera**: Δοκίμασε τη νέα κάμερα
5. **📊 Check Dashboard**: Εξερεύνησε το admin panel

---

## 🆘 **ΑΝ ΚΑΤΙ ΠΑΕΙ ΣΤΡΑΒΑ:**

### **Login Issues:**
```
- Δοκίμασε: admin / admin123
- Clear browser cache
- Ελέγξε ότι το app_v2.py ανέβηκε σωστά
```

### **Database Issues:**
```
- Railway logs θα δείξουν σφάλματα
- Νέα database δημιουργείται αυτόματα
- Default admin user θα υπάρχει
```

### **Camera Issues:**
```
- Δουλεύει μόνο σε HTTPS (Railway provides αυτόματα)
- Χρειάζεται permission από browser
- Fallback: Upload file option υπάρχει πάντα
```

---

# 🚀 **ΕΤΟΙΜΟΣ ΓΙΑ V2.0!**

**Αντιγράψε όλα τα αρχεία από τη λίστα και ανέβασέ τα στο GitHub!**