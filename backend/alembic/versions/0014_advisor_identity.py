"""Give the bundled advisor workspace a submission identity; retain source provenance."""
from alembic import op
import sqlalchemy as sa
revision='0014_advisor_identity'
down_revision='0013_connected_workspace'
branch_labels=None
depends_on=None

def upgrade():
    conn=op.get_bind()
    from app.core.security import hash_password,verify_password
    for old,new,name in [('advisor@advicue.demo','advisor@advicue.local','Advisor'),('admin@advicue.demo','admin@advicue.local','Workspace administrator')]:
        row=conn.execute(sa.text('SELECT id,password_hash FROM users WHERE email=:email'),{'email':old}).mappings().first()
        if row and not conn.execute(sa.text('SELECT id FROM users WHERE email=:email'),{'email':new}).first():
            password=hash_password('Advisor2026!') if verify_password(row['password_hash'],'AdviCueDemo2026!') else row['password_hash']
            conn.execute(sa.text('UPDATE users SET email=:email,name=:name,password_hash=:password WHERE id=:id'),dict(email=new,name=name,password=password,id=row['id']))
    conn.execute(sa.text("UPDATE organizations SET name='AdviCue Advisor Workspace' WHERE name='AdviCue Demo Organization'"))

def downgrade():
    # Account identity and presentation updates are intentionally not reversed.
    pass
