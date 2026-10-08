import os, sqlite3, json, csv, io, secrets, click
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, Response, jsonify
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
BASE=Path(__file__).resolve().parent
app=Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE','1')=='1',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=1024*1024)
if os.environ.get('TRUST_PROXY')=='1':
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app=ProxyFix(app.wsgi_app, x_for=1,x_proto=1,x_host=1)
csrf=CSRFProtect(app)
limiter=Limiter(get_remote_address,app=app,default_limits=['200 per hour'],storage_uri='memory://')
DB=Path(os.environ.get('DATABASE_PATH','instance/spotchecks.sqlite3'))
if not DB.is_absolute(): DB=BASE/DB
DB.parent.mkdir(parents=True, exist_ok=True)

SECTIONS=[
('Section One – On Arrival in the Home', []),
('Section Two – Care Plan', [
'Is the Care Worker aware of the Service User’s Care Plan and its updates?',
'Does the Care Worker check the Service User’s previous Visit Notes upon arrival?',
'Does the Care Worker seek the Service User’s consent before delivering any aspect of care?',
'Does the Care Worker know what care the Service User needs?']),
('Section Three – Safe Working Practices', [
'Does the Care Worker wash their hands before and after providing care and support?',
'Does the Care Worker use PPE correctly?',
'Is the Care Worker vigilant for hazards in the home?',
'Is any food handled correctly and hygienically?',
'Is the working area kept clean and tidy and is any PPE disposed of correctly?']),
('Section Four – Medication', [
'Is the MAR completed correctly?',
'Does the Care Worker follow the 6 Rights of Medication correctly?']),
('Section Five – Attitude and Behaviour', [
'Does the Care Worker communicate well with the Service User and evidence compassionate care?',
'Does the Care Worker respect the privacy of the Service User?',
'Does the Care Worker respect the dignity of the Service User?',
'Does the Care Worker allow the Service User to make their own choices?',
'Does the Care Worker work in an enabling way?']),
('Section Six – Recording', [
'Does the Care Worker accurately record on the care records the activities that have been undertaken?',
'Does the Care Worker log out correctly if electronic monitoring is used?']),
('Section Seven – Service User Feedback', [
'Do you know which Care Worker will be coming to visit you?',
'Does the Care Worker usually wear identification?',
'Does your Care Worker come on time?',
'Does the Care Worker respect your privacy and treat you with dignity?',
'Does the Care Worker usually wear gloves and plastic aprons for personal care?',
'Does the Care Worker make you feel comfortable and safe?',
'Do you feel in control of your care service? (Can you make your own choices?)',
'Do you know how to make a complaint?',
'If you have made a complaint, was it resolved?',
'Are you happy with the care you receive from Lovehands Care Services Limited?',
'Is there anything else you want to tell me about your care?'])]
MEDICATION_SECTIONS=[
 ('Training and Policy',[
 'Has the staff member completed the medication training set out by Lovehands Care?',
 'Has the staff member read the medication policy and signed to indicate they have done so?',
 'Does the staff member know how to access the medication policy should they need to?']),
 ('Administration of Medication',[
 'Did the staff member wash their hands or sanitise before putting on their gloves?',
 'Did the staff member ask for the client’s consent to administer their medication?',
 'Has the staff member checked the MAR chart to make sure they are giving the correct medication and dose at the right time?',
 'Did the staff member offer the client a drink to take their medication?',
 'Did the staff member observe the client taking their medication?',
 'Did the staff member record using the correct codes on the MAR chart?',
 'If the medication was not given, has the staff member recorded this correctly and raised a concern?',
 'Are there sufficient amounts of medication for the client’s needs?',
 'Is the medication stored safely?',
 'Has the staff member returned any medication to the fridge if needed?',
 'Is there any excess medication on the premises?',
 'Does the client take any PRN medication?',
 'Has the staff member recorded this correctly?',
 'Did the staff member remove their PPE in the correct way?',
 'Did the staff member wash their hands or sanitise after removing their gloves?',
 'Does the staff member know who to contact with any medication concerns?',
 'Can the staff member describe what to do if there is a medication error?',
 'Can the staff member describe what they would do if they discovered a medication error made by another care staff member?'])
]
MEDICATION_QUESTIONS=[(f'm{s}_{i}',q) for s,(_,items) in enumerate(MEDICATION_SECTIONS) for i,q in enumerate(items)]

QUESTIONS=[(f'q{s}_{i}',q) for s,(_,items) in enumerate(SECTIONS) for i,q in enumerate(items)]

def conn():
    c=sqlite3.connect(DB, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','assessor')), active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY, assessor_id INTEGER NOT NULL REFERENCES users(id), service_username TEXT NOT NULL, assessor_name TEXT NOT NULL, care_workers TEXT NOT NULL, reason TEXT NOT NULL, spot_date TEXT NOT NULL, scheduled_time TEXT, arrive_time TEXT, depart_time TEXT, outcome TEXT NOT NULL CHECK(outcome IN ('Passed','Failed')), responses TEXT NOT NULL, actions TEXT NOT NULL, signature TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS medication_assessments(id INTEGER PRIMARY KEY, assessor_id INTEGER NOT NULL REFERENCES users(id), staff_name TEXT NOT NULL, assessment_date TEXT NOT NULL, responses TEXT NOT NULL, notes TEXT NOT NULL, competent TEXT NOT NULL, extra_training TEXT NOT NULL, error_questions TEXT NOT NULL, assessor_name TEXT NOT NULL, assessor_signature TEXT NOT NULL, staff_signature TEXT NOT NULL, next_assessment TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, record_id INTEGER, created_at TEXT NOT NULL);
        ''')

init_db()  # Safe CREATE TABLE IF NOT EXISTS migration; existing records are preserved.

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def audit(c,action,record_id=None): c.execute('INSERT INTO audit_log(user_id,action,record_id,created_at) VALUES(?,?,?,?)',(session.get('uid'),action,record_id,now()))

def current_user():
    if not session.get('uid'): return None
    with conn() as c: return c.execute('SELECT id,username,full_name,role FROM users WHERE id=? AND active=1',(session['uid'],)).fetchone()

@app.context_processor
def context(): return {'user':current_user()}

@app.after_request
def secure_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    response.headers['Cache-Control']='no-store'
    return response

def login_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        if not current_user(): return redirect(url_for('login'))
        return fn(*a,**kw)
    return inner

def admin_required(fn):
    @wraps(fn)
    @login_required
    def inner(*a,**kw):
        if current_user()['role']!='admin': abort(403)
        return fn(*a,**kw)
    return inner

@app.route('/')
def index():
    u=current_user()
    if not u: return redirect(url_for('login'))
    return redirect(url_for('dashboard' if u['role']=='admin' else 'form_choice'))

@app.route('/login',methods=['GET','POST'])
@limiter.limit('8 per minute')
def login():
    if request.method=='POST':
        username=request.form.get('username','').strip()
        password=request.form.get('password','')
        with conn() as c: u=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
        if u and check_password_hash(u['password_hash'],password):
            session.clear();session['uid']=u['id'];session.permanent=True
            with conn() as c: audit(c,'login')
            return redirect(url_for('dashboard' if u['role']=='admin' else 'form_choice'))
        flash('Incorrect username or password.','error')
    return render_template('login.html')

@app.post('/logout')
@login_required
def logout():
    with conn() as c: audit(c,'logout')
    session.clear();return redirect(url_for('login'))

@app.get('/forms')
@login_required
def form_choice():
    return render_template('forms.html')

@app.route('/medication/new', methods=['GET','POST'])
@login_required
@limiter.limit('30 per hour')
def new_medication():
    u=current_user()
    if request.method=='GET':
        return render_template('medication_form.html',sections=MEDICATION_SECTIONS)
    get=lambda k: request.form.get(k,'').strip()
    errors=[]
    fields={k:get(k) for k in ('staff_name','assessment_date','notes','competent','extra_training','error_questions','assessor_signature','staff_signature','next_assessment')}
    if not all(fields[k] for k in ('staff_name','assessment_date','competent','extra_training','error_questions','assessor_signature','staff_signature','next_assessment')):
        errors.append('Complete all required details, outcomes and signatures')
    for date_key in ('assessment_date','next_assessment'):
        try: datetime.strptime(fields[date_key],'%Y-%m-%d')
        except ValueError: errors.append('Please enter valid dates')
    if len(fields['notes'])>10000 or any(len(fields[k])>160 for k in ('staff_name','assessor_signature','staff_signature')):
        errors.append('One or more text fields are too long')
    for key in ('competent','extra_training','error_questions'):
        if fields[key] not in ('Yes','No'):errors.append('Choose Yes or No for all three outcomes')
    answers={}
    for key,q in MEDICATION_QUESTIONS:
        answer=get(key)
        allowed=('Yes','No','N/A') if key=='m1_9' else ('Yes','No')
        if answer not in allowed: errors.append('Answer all medication assessment questions')
        comment=get(key+'_comment')
        if len(comment)>2000: errors.append('A comment is too long')
        answers[key]={'question':q,'answer':answer,'comment':comment}
    if errors:
        flash('; '.join(sorted(set(errors)))[:500],'error')
        return render_template('medication_form.html',sections=MEDICATION_SECTIONS,old=request.form),400
    with conn() as c:
        cur=c.execute("""INSERT INTO medication_assessments(assessor_id,staff_name,assessment_date,responses,notes,competent,extra_training,error_questions,assessor_name,assessor_signature,staff_signature,next_assessment,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (u['id'],fields['staff_name'],fields['assessment_date'],json.dumps(answers),fields['notes'],fields['competent'],fields['extra_training'],fields['error_questions'],u['full_name'],fields['assessor_signature'],fields['staff_signature'],fields['next_assessment'],now()))
        audit(c,'create_medication_assessment',cur.lastrowid)
    flash('Medication competency assessment submitted.','success')
    return redirect(url_for('medication_detail',assessment_id=cur.lastrowid))

@app.get('/medication/<int:assessment_id>')
@login_required
def medication_detail(assessment_id):
    u=current_user()
    with conn() as c:
        assessment=c.execute('SELECT * FROM medication_assessments WHERE id=?',(assessment_id,)).fetchone()
        if not assessment:abort(404)
        if u['role']!='admin' and assessment['assessor_id']!=u['id']:abort(403)
        audit(c,'view_medication_assessment',assessment_id)
    return render_template('medication_detail.html',s=assessment,responses=json.loads(assessment['responses']),sections=MEDICATION_SECTIONS)

@app.get('/medication/export.csv')
@admin_required
def export_medication_csv():
    with conn() as c:
        rows=c.execute('SELECT * FROM medication_assessments ORDER BY created_at DESC').fetchall()
        audit(c,'export_medication_csv')
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['ID','Submitted UTC','Assessment date','Staff member','Assessor','Competent','Extra training','Answered errors','Next assessment','Notes']+[q for _,q in MEDICATION_QUESTIONS])
    for r in rows:
        data=json.loads(r['responses'])
        writer.writerow([r['id'],r['created_at'],r['assessment_date'],r['staff_name'],r['assessor_name'],r['competent'],r['extra_training'],r['error_questions'],r['next_assessment'],r['notes']]+[data.get(k,{}).get('answer','')+' | '+data.get(k,{}).get('comment','') for k,_ in MEDICATION_QUESTIONS])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=lovehands-medication-assessments.csv'})

@app.route('/new',methods=['GET','POST'])
@login_required
@limiter.limit('30 per hour')
def new_check():
    u=current_user()
    if request.method=='GET': return render_template('form.html',sections=SECTIONS,questions=QUESTIONS)
    get=lambda k:request.form.get(k,'').strip()
    fields={k:get(k) for k in ('service_username','care_workers','reason','spot_date','scheduled_time','arrive_time','depart_time','outcome','signature')}
    errors=[]
    for k in ('service_username','care_workers','reason','spot_date','outcome','signature'):
        if not fields[k]:errors.append(k.replace('_',' ').title()+' is required')
    if fields['outcome'] not in ('Passed','Failed'):errors.append('Choose an outcome')
    try: datetime.strptime(fields['spot_date'],'%Y-%m-%d')
    except ValueError: errors.append('Enter a valid spot check date')
    if any(len(v)>500 for k,v in fields.items() if k!='signature'): errors.append('One or more fields are too long')
    if len(fields['signature'])>150:errors.append('Signature name too long')
    responses={}
    for k,q in QUESTIONS:
        answer=get(k);comment=get(k+'_comment')
        if answer not in ('Yes','No','N/A'): errors.append('Answer all questionnaire items')
        if len(comment)>2000:errors.append('Comment too long')
        responses[k]={'question':q,'answer':answer,'comment':comment}
    actions=[]
    for i in range(1,8):
        action=get(f'action_{i}');by=get(f'action_by_{i}')
        if len(action)>2000 or len(by)>160: errors.append('Action plan entry too long')
        if action or by:actions.append({'number':i,'action':action,'by':by,'status':'Pending' if action else 'Not applicable'})
    if errors:
        flash('; '.join(sorted(set(errors)))[:500],'error')
        return render_template('form.html',sections=SECTIONS,questions=QUESTIONS,old=request.form),400
    with conn() as c:
        cur=c.execute('''INSERT INTO submissions(assessor_id,service_username,assessor_name,care_workers,reason,spot_date,scheduled_time,arrive_time,depart_time,outcome,responses,actions,signature,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
             (u['id'],fields['service_username'],u['full_name'],fields['care_workers'],fields['reason'],fields['spot_date'],fields['scheduled_time'],fields['arrive_time'],fields['depart_time'],fields['outcome'],json.dumps(responses),json.dumps(actions),fields['signature'],now()))
        audit(c,'create_submission',cur.lastrowid)
    flash('Spot check submitted successfully.','success')
    return redirect(url_for('detail',check_id=cur.lastrowid))

@app.get('/dashboard')
@admin_required
def dashboard():
    term=request.args.get('q','').strip()[:100]
    outcome=request.args.get('outcome','')
    form_type=request.args.get('form_type','')
    with conn() as c:
        spots=c.execute('SELECT * FROM submissions ORDER BY created_at DESC LIMIT 500').fetchall()
        meds=c.execute('SELECT * FROM medication_assessments ORDER BY created_at DESC LIMIT 500').fetchall()
    records=[]
    for r in spots:
        records.append(dict(id=r['id'],form_type='spot',date=r['spot_date'],person=r['service_username'],staff=r['care_workers'],assessor=r['assessor_name'],outcome=r['outcome'],created_at=r['created_at']))
    for r in meds:
        records.append(dict(id=r['id'],form_type='medication',date=r['assessment_date'],person=r['staff_name'],staff=r['staff_name'],assessor=r['assessor_name'],outcome='Competent' if r['competent']=='Yes' else 'Not competent',created_at=r['created_at']))
    totals={'spot':len(spots),'medication':len(meds),'all':len(spots)+len(meds)}
    if form_type in ('spot','medication'):records=[r for r in records if r['form_type']==form_type]
    if term:records=[r for r in records if term.lower() in ' '.join([r['person'],r['staff'],r['assessor']]).lower()]
    if outcome:records=[r for r in records if r['outcome']==outcome]
    records=sorted(records,key=lambda r:r['created_at'],reverse=True)[:500]
    return render_template('dashboard.html',checks=records,totals=totals,term=term,outcome=outcome,form_type=form_type)

@app.get('/check/<int:check_id>')
@login_required
def detail(check_id):
    u=current_user()
    with conn() as c:
        s=c.execute('SELECT * FROM submissions WHERE id=?',(check_id,)).fetchone()
        if not s:abort(404)
        if u['role']!='admin' and s['assessor_id']!=u['id']:abort(403)
        audit(c,'view_submission',check_id)
    return render_template('detail.html',s=s,responses=json.loads(s['responses']),actions=json.loads(s['actions']),sections=SECTIONS)

@app.get('/export.csv')
@admin_required
def export_csv():
    with conn() as c:
        rows=c.execute('SELECT * FROM submissions ORDER BY created_at DESC').fetchall()
        audit(c,'export_csv')
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['ID','Submitted UTC','Spot Date','Service Username','Assessor','Care Workers','Reason','Outcome','Scheduled','Arrived','Departed','Actions']+[q for _,q in QUESTIONS])
    for r in rows:
        data=json.loads(r['responses'])
        writer.writerow([r['id'],r['created_at'],r['spot_date'],r['service_username'],r['assessor_name'],r['care_workers'],r['reason'],r['outcome'],r['scheduled_time'],r['arrive_time'],r['depart_time'],json.dumps(json.loads(r['actions']))]+[data.get(k,{}).get('answer','')+' | '+data.get(k,{}).get('comment','') for k,_ in QUESTIONS])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=lovehands-spot-checks.csv'})

@app.route('/users',methods=['GET','POST'])
@admin_required
def users():
    if request.method=='POST':
        username=request.form.get('username','').strip();name=request.form.get('full_name','').strip()
        password=request.form.get('password','');role=request.form.get('role','')
        if not (3<=len(username)<=80 and 2<=len(name)<=120 and len(password)>=12 and role in ('admin','assessor')):
            flash('Provide a username (3+ characters), name, password (12+ characters) and valid role.','error')
        else:
            try:
                with conn() as c:
                    cur=c.execute('INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)',(username,name,generate_password_hash(password),role,now()))
                    audit(c,'create_user',cur.lastrowid)
                flash('User account created.','success')
            except sqlite3.IntegrityError: flash('Username already exists.','error')
        return redirect(url_for('users'))
    with conn() as c: people=c.execute('SELECT id,username,full_name,role,active,created_at FROM users ORDER BY id').fetchall()
    return render_template('users.html',people=people)

@app.post('/users/<int:user_id>/toggle')
@admin_required
def toggle_user(user_id):
    if user_id==current_user()['id']:abort(400,'You cannot deactivate yourself')
    with conn() as c:
        u=c.execute('SELECT active FROM users WHERE id=?',(user_id,)).fetchone()
        if not u:abort(404)
        c.execute('UPDATE users SET active=? WHERE id=?',(0 if u['active'] else 1,user_id));audit(c,'toggle_user',user_id)
    return redirect(url_for('users'))

@app.cli.command('init-db')
def init_db_command():
    init_db();click.echo('Database initialized')

@app.cli.command('create-admin')
@click.option('--username',prompt=True)
@click.option('--name',prompt='Full name')
@click.password_option(confirmation_prompt=True)
def create_admin(username,name,password):
    if len(password)<12:raise click.ClickException('Password must be at least 12 characters')
    with conn() as c:
        c.execute('INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)',(username.strip(),name.strip(),generate_password_hash(password),'admin',now()))
    click.echo('Administrator created')

if __name__=='__main__':
    app.run(debug=False)
