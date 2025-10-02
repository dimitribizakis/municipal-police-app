-- Migration Script: Προσθήκη στήλης related_message_id στον πίνακα notification
-- Ημερομηνία: 02/10/2025
-- Περιγραφή: Προσθήκη στήλης για σύνδεση ειδοποιήσεων με μηνύματα

-- Προσθήκη της νέας στήλης
ALTER TABLE notification ADD COLUMN related_message_id INTEGER;

-- Προσθήκη foreign key constraint
ALTER TABLE notification ADD CONSTRAINT fk_notification_message_id 
    FOREIGN KEY (related_message_id) REFERENCES message (id);

-- Δημιουργία index για καλύτερη απόδοση
CREATE INDEX idx_notification_related_message_id ON notification(related_message_id);