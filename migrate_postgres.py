from app import db
from sqlalchemy import text

def run_migration():
    print('🔄 Starting PostgreSQL migration...')
    
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
    
    success_count = 0
    for cmd in commands:
        try:
            db.session.execute(text(cmd))
            print(f'✅ {cmd}')
            success_count += 1
        except Exception as e:
            print(f'⚠️ {cmd} - Error: {str(e)[:100]}...')
    
    db.session.commit()
    print(f'🎉 Migration completed! {success_count}/{len(commands)} commands executed successfully.')

if __name__ == '__main__':
    run_migration()