from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
import re
import random
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chiave_super_segreta_tutor_fisica_2024')

# --- CONNESSIONE SUPABASE/POSTGRESQL ---
DB_HOST = os.environ.get('DB_HOST', '')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'postgres')
DB_USER = os.environ.get('DB_USER', '')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# --- CONFIGURAZIONE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Effettua il login per accedere alla piattaforma."

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM utenti WHERE id = %s', (user_id,))
    user = cur.fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'])
    return None

def pulisci_domanda(testo_grezzo):
    testo_pulito = re.sub(r'%\s*Domanda\s*\d+', '', testo_grezzo).strip()
    testo_pulito = re.sub(r'\\vspace\{.*?\}', '', testo_pulito)
    testo_pulito = re.sub(r'\\setcounter\{.*?\}\{.*?\}', '', testo_pulito)
    testo_pulito = testo_pulito.replace(r'\end{multicols*}', '')
    testo_pulito = testo_pulito.replace(r'\newpage', '')
    testo_pulito = testo_pulito.strip()

    matches_begin = list(re.finditer(r'\\begin\{enumerate\}', testo_pulito))

    if matches_begin:
        last_match = matches_begin[-1]
        idx_begin = last_match.start()
        domanda_testo = testo_pulito[:idx_begin].strip()
        domanda_testo = domanda_testo.replace(r'\item', '', 1).strip()
        domanda_testo = re.sub(r'\\begin\{enumerate\}\[.*?Roman.*?\]', '<ol type="I" class="fw-normal ps-4 mt-3 mb-3">', domanda_testo)
        domanda_testo = re.sub(r'\\begin\{enumerate\}.*?\]?', '<ol class="fw-normal ps-4 mt-3 mb-3">', domanda_testo)
        domanda_testo = domanda_testo.replace(r'\end{enumerate}', '</ol>')
        domanda_testo = domanda_testo.replace(r'\item', '<li class="mb-2">')

        blocco_opzioni = testo_pulito[idx_begin:]
        idx_end = blocco_opzioni.find(r'\end{enumerate}')
        if idx_end != -1:
            blocco_opzioni = blocco_opzioni[:idx_end]

        blocco_opzioni = re.sub(r'\\begin\{enumerate\}(\[.*?\])?', '', blocco_opzioni)
        opzioni_str = blocco_opzioni.split(r'\item')
        opzioni = [opt.strip() for opt in opzioni_str if opt.strip()]
        return {"testo": domanda_testo, "opzioni": opzioni}
    else:
        testo_pulito = testo_pulito.replace(r'\item', '', 1).strip()
        return {"testo": testo_pulito, "opzioni": []}

# --- AUTENTICAZIONE ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        conn = get_db_connection()
        cur = get_cursor(conn)
        try:
            cur.execute('INSERT INTO utenti (username, password) VALUES (%s, %s)', (username, hashed_password))
            conn.commit()
            flash('Registrazione completata! Ora puoi fare il login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash('Nome utente già in uso. Scegline un altro.', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = get_cursor(conn)
        cur.execute('SELECT * FROM utenti WHERE username = %s', (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            login_user(User(user['id'], user['username']))
            return redirect(url_for('index'))
        else:
            flash('Nome utente o password errati.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ROTTE PRINCIPALI ---
@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT COUNT(*) as cnt FROM domande')
    totale = cur.fetchone()['cnt']
    cur.execute('SELECT * FROM simulazioni WHERE id_utente = %s ORDER BY data_test DESC LIMIT 10', (current_user.id,))
    storico_grezzo = cur.fetchall()
    conn.close()

    # --- CORREZIONE DATE PER POSTGRESQL ---
    # Convertiamo l'oggetto datetime in una stringa di testo
    # così l'index.html può usare .split() senza andare in crash
    storico_pulito = []
    for s in storico_grezzo:
        s_dict = dict(s)
        s_dict['data_test'] = str(s_dict['data_test'])
        storico_pulito.append(s_dict)
    # --------------------------------------

    return render_template('index.html', totale=totale, storico=storico_pulito, nome_utente=current_user.username)

@app.route('/simulazione')
@login_required
def simulazione():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT DISTINCT capitolo FROM domande WHERE capitolo IS NOT NULL')
    capitoli_db = cur.fetchall()
    capitoli = [c['capitolo'] for c in capitoli_db if c['capitolo'].strip() != ""]
    domande_db = []

    if not capitoli:
        cur.execute('SELECT * FROM domande ORDER BY RANDOM() LIMIT 31')
        domande_db = cur.fetchall()
    else:
        q_per_capitolo = 31 // len(capitoli)
        resto = 31 % len(capitoli)
        for i, capitolo in enumerate(capitoli):
            limite = q_per_capitolo + (1 if i < resto else 0)
            cur.execute('SELECT * FROM domande WHERE capitolo = %s ORDER BY RANDOM() LIMIT %s', (capitolo, limite))
            domande_db.extend(cur.fetchall())

        mancanti = 31 - len(domande_db)
        if mancanti > 0:
            id_selezionati = [d['id'] for d in domande_db]
            cur.execute('SELECT * FROM domande WHERE id != ALL(%s) ORDER BY RANDOM() LIMIT %s', (id_selezionati, mancanti))
            domande_db.extend(cur.fetchall())
        random.shuffle(domande_db)
    conn.close()

    test_completo = []
    for d in domande_db:
        d_dict = dict(d)
        parti_pulite = pulisci_domanda(d_dict['testo'])
        d_dict['testo_pulito'] = parti_pulite['testo']
        d_dict['lista_opzioni'] = parti_pulite['opzioni']
        test_completo.append(d_dict)
    return render_template('simulazione.html', domande=test_completo, tipo_simulazione='classica')

@app.route('/simulazione_personalizzata')
@login_required
def simulazione_personalizzata():
    num_domande = request.args.get('num_domande', default=30, type=int)
    minuti = request.args.get('minuti', default=45, type=int)

    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM domande WHERE fonte = %s ORDER BY RANDOM() LIMIT %s', ('personalizzata', num_domande))
    domande_db = cur.fetchall()
    conn.close()

    if not domande_db:
        flash("Nessuna domanda trovata per la Prova Esame 1cfu.", "danger")
        return redirect(url_for('index'))

    test_completo = []
    for d in domande_db:
        d_dict = dict(d)
        parti_pulite = pulisci_domanda(d_dict['testo'])
        d_dict['testo_pulito'] = parti_pulite['testo']
        d_dict['lista_opzioni'] = parti_pulite['opzioni']
        test_completo.append(d_dict)

    return render_template('simulazione.html', domande=test_completo, minuti_timer=minuti, totale_domande=num_domande, tipo_simulazione='personalizzata')

@app.route('/salva_simulazione', methods=['POST'])
@login_required
def salva_simulazione():
    try:
        dati = request.get_json(silent=True)
        
        if dati:
            # Caso A: Invio tramite Javascript JSON
            risposte_utente = dati.get('risposte', {})
            tipo_simulazione = dati.get('tipo_simulazione', 'classica')
        else:
            # Caso B: Invio tramite form classico
            form_data = request.form.to_dict()
            # Estraiamo il tipo di simulazione ed evitiamo che venga letto come ID domanda
            tipo_simulazione = form_data.pop('tipo_simulazione', 'classica')
            risposte_utente = form_data

        # --- IMPOSTAZIONE DELLA PENALITÀ CORRETTA ---
        penalita_errore = 0.0 if tipo_simulazione == 'personalizzata' else -0.1

        conn = get_db_connection()
        cur = get_cursor(conn)

        punteggio = 0.0; corrette = 0; errate = 0; non_date = 0
        dettagli_da_salvare = []; dettagli_frontend = []

        for id_dom_str, risposta_data in risposte_utente.items():
            # Salta eventuali chiavi spurie che non sono ID numerici
            if not id_dom_str.isdigit(): continue
            
            id_dom = int(id_dom_str)
            cur.execute('SELECT testo, risposta_corretta FROM domande WHERE id = %s', (id_dom,))
            domanda = cur.fetchone()
            if not domanda: continue
            risposta_esatta = domanda['risposta_corretta']
            testo_domanda = pulisci_domanda(domanda['testo'])['testo']
            allowed_answers = ['A', 'B', 'C', 'D', 'E']
            
            # Normalizziamo la risposta eliminando spazi bianchi
            if risposta_data:
                risposta_data = str(risposta_data).strip().upper()
                if risposta_data not in allowed_answers:
                    risposta_data = None

            esito = 'non_data'
            if risposta_data:
                if risposta_data == risposta_esatta:
                    esito = 'corretta'
                    punteggio += 1.0
                    corrette += 1
                else:
                    esito = 'errata'
                    punteggio += penalita_errore  # Applica 0.0 o -0.1 a seconda della modalità
                    errate += 1
            else:
                non_date += 1

            dettagli_da_salvare.append((id_dom, risposta_data, esito))
            dettagli_frontend.append({
                "id_domanda": id_dom,
                "testo_domanda": testo_domanda,
                "risposta_data": risposta_data if risposta_data else "Nessuna",
                "risposta_esatta": risposta_esatta,
                "esito": esito
            })

        cur.execute(
            '''INSERT INTO simulazioni 
               (punteggio_totale, corrette, errate, non_date, id_utente, data_test) 
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id''',
            (round(punteggio, 2), corrette, errate, non_date, current_user.id)
        )
        id_simulazione = cur.fetchone()['id']

        for dett in dettagli_da_salvare:
            cur.execute(
                'INSERT INTO dettagli_simulazione (id_simulazione, id_domanda, risposta_data, esito) VALUES (%s, %s, %s, %s)',
                (id_simulazione, dett[0], dett[1], dett[2])
            )

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "punteggio": round(punteggio, 2), "corrette": corrette, "errate": errate, "non_date": non_date, "dettagli": dettagli_frontend})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/statistiche_capitoli')
@login_required
def statistiche_capitoli():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT d.capitolo,
               SUM(CASE WHEN ds.esito = 'errata' THEN 1 ELSE 0 END) as errate,
               SUM(CASE WHEN ds.esito = 'non_data' THEN 1 ELSE 0 END) as omesse
        FROM dettagli_simulazione ds
        JOIN domande d ON ds.id_domanda = d.id
        JOIN simulazioni s ON ds.id_simulazione = s.id
        WHERE s.id_utente = %s
        GROUP BY d.capitolo
        HAVING (SUM(CASE WHEN ds.esito = 'errata' THEN 1 ELSE 0 END) + SUM(CASE WHEN ds.esito = 'non_data' THEN 1 ELSE 0 END)) > 0
        ORDER BY (SUM(CASE WHEN ds.esito = 'errata' THEN 1 ELSE 0 END) + SUM(CASE WHEN ds.esito = 'non_data' THEN 1 ELSE 0 END)) DESC
        LIMIT 8
    ''', (current_user.id,))
    dati = cur.fetchall()
    conn.close()
    return jsonify([dict(row) for row in dati])

@app.route('/resoconto/<int:id_simulazione>')
@login_required
def resoconto(id_simulazione):
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM simulazioni WHERE id = %s AND id_utente = %s', (id_simulazione, current_user.id))
    sim = cur.fetchone()
    if not sim:
        conn.close()
        return "Simulazione non trovata o accesso negato", 404
    cur.execute('''
        SELECT ds.*, d.testo, d.risposta_corretta, d.capitolo
        FROM dettagli_simulazione ds
        JOIN domande d ON ds.id_domanda = d.id
        WHERE ds.id_simulazione = %s ORDER BY ds.id ASC
    ''', (id_simulazione,))
    dettagli_db = cur.fetchall()
    conn.close()

    dettagli_puliti = []
    for d in dettagli_db:
        d_dict = dict(d)
        parti_pulite = pulisci_domanda(d_dict['testo'])
        d_dict['testo_pulito'] = parti_pulite['testo']
        d_dict['lista_opzioni'] = parti_pulite['opzioni']
        dettagli_puliti.append(d_dict)
    return render_template('resoconto.html', simulazione=sim, dettagli=dettagli_puliti)

@app.route('/quiz')
@login_required
def quiz():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM domande ORDER BY RANDOM() LIMIT 1')
    domanda_db = cur.fetchone()
    conn.close()

    if domanda_db:
        domanda_dict = dict(domanda_db)
        parti_pulite = pulisci_domanda(domanda_dict['testo'])
        domanda_dict['testo_pulito'] = parti_pulite['testo']
        domanda_dict['lista_opzioni'] = parti_pulite['opzioni']
        return render_template('quiz.html', domanda=domanda_dict, modalita='quiz')
    return "Nessuna domanda trovata."

@app.route('/palestra')
@login_required
def palestra():
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    # --- CORREZIONE POSTGRESQL ---
    # Usiamo "WITH" per creare un cesto temporaneo di domande uniche
    # e poi peschiamo a caso (ORDER BY RANDOM) da quel cesto.
    cur.execute('''
        WITH domande_uniche AS (
            SELECT DISTINCT d.* FROM domande d
            JOIN dettagli_simulazione ds ON d.id = ds.id_domanda
            JOIN simulazioni s ON ds.id_simulazione = s.id
            LEFT JOIN statistiche st ON d.id = st.id_domanda AND st.id_utente = %s
            WHERE s.id_utente = %s AND ds.esito IN ('errata', 'non_data')
            AND (st.volte_corretta IS NULL OR st.volte_corretta = 0)
        )
        SELECT * FROM domande_uniche ORDER BY RANDOM() LIMIT 1
    ''', (current_user.id, current_user.id))
    
    domanda_db = cur.fetchone()
    conn.close()

    if domanda_db:
        domanda_dict = dict(domanda_db)
        parti_pulite = pulisci_domanda(domanda_dict['testo'])
        domanda_dict['testo_pulito'] = parti_pulite['testo']
        domanda_dict['lista_opzioni'] = parti_pulite['opzioni']
        return render_template('quiz.html', domanda=domanda_dict, modalita='palestra')
    return render_template('quiz.html', vuota=True)

@app.route('/registra_statistica', methods=['POST'])
@login_required
def registra_statistica():
    data = request.json
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM statistiche WHERE id_domanda = %s AND id_utente = %s', (data['id_domanda'], current_user.id))
    stat = cur.fetchone()
    colonna = 'volte_corretta' if data['esito'] == 'corretta' else 'volte_sbagliata'

    if stat:
        cur.execute(f'UPDATE statistiche SET {colonna} = {colonna} + 1 WHERE id_domanda = %s AND id_utente = %s', (data['id_domanda'], current_user.id))
    else:
        if data['esito'] == 'corretta':
            cur.execute('INSERT INTO statistiche (id_domanda, id_utente, volte_corretta, volte_sbagliata) VALUES (%s, %s, 1, 0)', (data['id_domanda'], current_user.id))
        else:
            cur.execute('INSERT INTO statistiche (id_domanda, id_utente, volte_corretta, volte_sbagliata) VALUES (%s, %s, 0, 1)', (data['id_domanda'], current_user.id))

    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=False)
