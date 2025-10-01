# ============= TEMPORARY MIGRATION ROUTE =============
@app.route('/admin/run-migration', methods=['GET', 'POST'])
def run_migration():
    """ΠΡΟΣΩΡΙΝΗ ROUTE ΓΙΑ MIGRATION - ΘΑ ΑΦΑΙΡΕΘΕΙ ΜΕΤΑ"""
    if request.method == 'POST':
        try:
            from sqlalchemy import text
            
            print("🔄 Starting PostgreSQL migration...")
            
            commands = [
                'ALTER TABLE violations_data ADD COLUMN article TEXT',
                'ALTER TABLE violations_data ADD COLUMN article_paragraph TEXT',
                'ALTER TABLE violations_data ADD COLUMN remove_circulation_elements BOOLEAN DEFAULT FALSE',
                'ALTER TABLE violations_data ADD COLUMN circulation_removal_days INTEGER DEFAULT 0',
                'ALTER TABLE violations_data ADD COLUMN remove_circulation_license BOOLEAN DEFAULT FALSE',
                'ALTER TABLE violations_data ADD COLUMN circulation_license_removal_days INTEGER DEFAULT 0',
                'ALTER TABLE violations_data ADD COLUMN remove_driving_license BOOLEAN DEFAULT FALSE',
                'ALTER TABLE violations_data ADD COLUMN driving_license_removal_days INTEGER DEFAULT 0',
                'ALTER TABLE violations_data ADD COLUMN half_fine_motorcycles BOOLEAN DEFAULT FALSE',
                'ALTER TABLE violations_data ADD COLUMN parking_special_provision BOOLEAN DEFAULT FALSE',
                'ALTER TABLE violations_data ADD COLUMN is_active BOOLEAN DEFAULT TRUE'
            ]
            
            results = []
            success_count = 0
            
            for cmd in commands:
                try:
                    db.session.execute(text(cmd))
                    column_name = cmd.split()[4]
                    results.append(f'✅ Added column: {column_name}')
                    success_count += 1
                except Exception as e:
                    column_name = cmd.split()[4]
                    results.append(f'⚠️ Column {column_name} already exists or error: {str(e)[:100]}...')
            
            db.session.commit()
            results.append(f'🎉 Migration completed! Successfully added {success_count} columns')
            
            return '<br>'.join(results) + '<br><br><a href="/admin/dashboard">← Back to Admin Dashboard</a>'
            
        except Exception as e:
            return f'❌ Migration failed: {str(e)}<br><br><a href="/admin/dashboard">← Back to Admin Dashboard</a>'
    
    return '''
    <div style="max-width: 600px; margin: 50px auto; padding: 20px; font-family: Arial;">
        <h2>🚀 Database Migration</h2>
        <p>This will add new columns to the violations_data table:</p>
        <ul>
            <li>article (TEXT)</li>
            <li>article_paragraph (TEXT)</li>
            <li>remove_circulation_elements (BOOLEAN)</li>
            <li>circulation_removal_days (INTEGER)</li>
            <li>remove_circulation_license (BOOLEAN)</li>
            <li>circulation_license_removal_days (INTEGER)</li>
            <li>remove_driving_license (BOOLEAN)</li>
            <li>driving_license_removal_days (INTEGER)</li>
            <li>half_fine_motorcycles (BOOLEAN)</li>
            <li>parking_special_provision (BOOLEAN)</li>
            <li>is_active (BOOLEAN)</li>
        </ul>
        <form method="post">
            <button type="submit" style="background-color: #dc3545; color: white; padding: 15px 30px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                🚨 RUN MIGRATION NOW
            </button>
        </form>
        <br>
        <a href="/admin/dashboard">← Back to Admin Dashboard</a>
    </div>
    '''

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
