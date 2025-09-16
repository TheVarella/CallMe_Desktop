import sys
import sqlite3
import hashlib
import csv
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QStackedWidget, QMessageBox, QComboBox,
    QTableWidget, QTableWidgetItem, QFileDialog, QHeaderView, QFrame, QTabWidget, QSplashScreen, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap, QIcon, QColor

# --- PDF generation imports (ReportLab) ---
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

DB_FILE = "chamados.db"


# ----------------------- Classe de Aviso Reutilizável -----------------------
class ConfirmDialog:
    @staticmethod
    def ask(parent, message: str) -> bool:
        """Exibe uma caixa de diálogo de confirmação.
        Retorna True se o usuário clicar em 'Sim', False se clicar em 'Não'."""
        dialog = QMessageBox(parent)
        dialog.setWindowTitle("Confirmação")
        dialog.setText(message)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = dialog.exec()
        return result == QMessageBox.StandardButton.Yes
    



# ----------------------- Banco de dados -----------------------
class Database:
    def __init__(self, db_file=DB_FILE):
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS res (
                id INTEGER PRIMARY KEY,
                re TEXT UNIQUE,
                role TEXT CHECK(role IN ('funcionario','tecnico'))
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                role TEXT CHECK(role IN ('funcionario','tecnico')),
                re TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY,
                title TEXT,
                description TEXT,
                status TEXT,
                created_by INTEGER,
                created_at TEXT,
                resolution TEXT,
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
        ''')
        self.conn.commit()
        self._ensure_sample_res()

    def _ensure_sample_res(self):
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM res")
        if c.fetchone()[0] == 0:
            for i in range(1, 11):
                re = f"FUNC{i:03d}"
                c.execute("INSERT INTO res (re, role) VALUES (?,?)", (re, 'funcionario'))
            for i in range(1, 4):
                re = f"TEC{i:03d}"
                c.execute("INSERT INTO res (re, role) VALUES (?,?)", (re, 'tecnico'))
            self.conn.commit()

    def create_user(self, name, email, password_hash, role, re):
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO users (name,email,password_hash,role,re) VALUES (?,?,?,?,?)",
                      (name, email, password_hash, role, re))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def find_user_by_email(self, email):
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        return c.fetchone()

    def get_user_by_id(self, uid):
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE id=?", (uid,))
        return c.fetchone()

    def update_user(self, uid, name, email):
        c = self.conn.cursor()
        c.execute("UPDATE users SET name=?, email=? WHERE id=?", (name, email, uid))
        self.conn.commit()

    def check_re(self, re):
        c = self.conn.cursor()
        c.execute("SELECT * FROM res WHERE re=?", (re,))
        return c.fetchone()

    def create_ticket(self, title, description, created_by):
        c = self.conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO tickets (title,description,status,created_by,created_at,resolution) VALUES (?,?,?,?,?,?)",
                  (title, description, 'Aberto', created_by, now, ''))
        self.conn.commit()
        return c.lastrowid

    # status_filter (usado pelo técnico)
    def get_tickets_for_user(self, user, status_filter=None):
        c = self.conn.cursor()
        if user['role'] == 'tecnico':
            query = "SELECT t.*, u.name as creator_name FROM tickets t JOIN users u ON t.created_by = u.id"
            params = []
            if status_filter and status_filter != "Todos":
                query += " WHERE t.status=?"
                params.append(status_filter)
            query += " ORDER BY t.created_at DESC"
            c.execute(query, params)
        else:
            c.execute("SELECT t.*, u.name as creator_name FROM tickets t JOIN users u ON t.created_by = u.id WHERE created_by=? ORDER BY t.created_at DESC", (user['id'],))
        return c.fetchall()

    def get_ticket(self, tid):
        c = self.conn.cursor()
        c.execute("SELECT t.*, u.name as creator_name, u.email as creator_email FROM tickets t JOIN users u ON t.created_by = u.id WHERE t.id=?", (tid,))
        return c.fetchone()

    def update_ticket_status(self, tid, status, resolution=None):
        c = self.conn.cursor()
        if resolution is not None:
            c.execute("UPDATE tickets SET status=?, resolution=? WHERE id=?", (status, resolution, tid))
        else:
            c.execute("UPDATE tickets SET status=? WHERE id=?", (status, tid))
        self.conn.commit()

    def export_tickets_csv(self, filepath, user_id=None):
        c = self.conn.cursor()
        if user_id:
            c.execute("SELECT t.id, t.title, t.description, t.status, t.created_at, t.resolution, u.name as creator_name, u.email FROM tickets t JOIN users u ON t.created_by = u.id WHERE t.created_by=? ORDER BY t.created_at DESC", (user_id,))
        else:
            c.execute("SELECT t.id, t.title, t.description, t.status, t.created_at, t.resolution, u.name as creator_name, u.email FROM tickets t JOIN users u ON t.created_by = u.id ORDER BY t.created_at DESC")
        rows = c.fetchall()
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id','title','description','status','created_at','resolution','creator_name','creator_email'])
            for r in rows:
                writer.writerow([r['id'], r['title'], r['description'], r['status'], r['created_at'], r['resolution'], r['creator_name'], r['email']])

    def export_tickets_pdf(self, filepath, user_id=None):
        """
        Export tickets to a PDF file using ReportLab.
        If user_id is provided, only that user's tickets are exported.
        """
        c = self.conn.cursor()
        if user_id:
            c.execute("SELECT t.id, t.title, t.description, t.status, t.created_at, t.resolution, u.name as creator_name, u.email FROM tickets t JOIN users u ON t.created_by = u.id WHERE t.created_by=? ORDER BY t.created_at DESC", (user_id,))
        else:
            c.execute("SELECT t.id, t.title, t.description, t.status, t.created_at, t.resolution, u.name as creator_name, u.email FROM tickets t JOIN users u ON t.created_by = u.id ORDER BY t.created_at DESC")
        rows = c.fetchall()

        # Create PDF
        doc = SimpleDocTemplate(filepath, pagesize=A4,
                                rightMargin=20*mm, leftMargin=20*mm,
                                topMargin=20*mm, bottomMargin=20*mm)
        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        normal.fontSize = 9
        heading = styles["Heading1"]
        heading.fontSize = 16

        elements = []

        # Try to add logo if available
        try:
            logo_path = "assets/logo.png"
            # small width; keep aspect ratio
            logo = RLImage(logo_path, width=40*mm, height=15*mm)
            elements.append(logo)
        except Exception:
            # ignore if missing
            pass

        elements.append(Spacer(1, 6))

        # Title and date
        title_par = Paragraph("Relatório de Chamados", heading)
        elements.append(title_par)
        elements.append(Spacer(1, 4))
        date_par = Paragraph(f"Emitido em: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} (UTC)", normal)
        elements.append(date_par)
        elements.append(Spacer(1, 8))

        # Table header
        data = []
        header = ['ID', 'Título', 'Descrição', 'Status', 'Criado por', 'Data', 'Resolução']
        data.append(header)

        # Build rows with Paragraphs for wrapping long text
        for r in rows:
            desc = r['description'] or ""
            resolution = r['resolution'] or ""
            created_at = r['created_at'] or ""
            row = [
                str(r['id']),
                Paragraph(r['title'] or "", normal),
                Paragraph(desc.replace('\n', '<br />'), normal),
                r['status'] or "",
                Paragraph(r['creator_name'] or "", normal),
                Paragraph(created_at, normal),
                Paragraph(resolution.replace('\n', '<br />'), normal)
            ]
            data.append(row)

        # Column widths (approx, in points)
        page_width = A4[0] - (40*mm)  # A4 width minus left+right margins
        # define relative widths: ID small, Title medium, Desc big, Status small, Creator small, Date small, Resolution medium
        col_widths = [
            30,                # ID
            90,                # Title
            200,               # Description
            60,                # Status
            80,                # Creator
            80,                # Date
            page_width - (30+90+200+60+80+80)  # Resolution: remaining
        ]

        # Ensure no negative widths
        col_widths = [w if w > 20 else 60 for w in col_widths]

        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0055ff")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (0,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('INNERGRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ])
        tbl.setStyle(tbl_style)

        elements.append(tbl)

        # Build PDF
        doc.build(elements)

    # ----------------------
    # Função para recuperação de senha
    # ----------------------
    def update_password_by_email_re(self, email, re_val, new_password_hash):
        """
        Verifica se existe usuário com email e re correspondentes e atualiza a senha.
        Retorna True se atualizado, False caso contrário.
        """
        c = self.conn.cursor()
        c.execute("SELECT id, re FROM users WHERE email=?", (email,))
        row = c.fetchone()
        if not row:
            return False
        if row['re'] != re_val:
            return False
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_password_hash, row['id']))
        self.conn.commit()
        return True

# ----------------------- Segurança -----------------------
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

# ----------------------- Login -----------------------
class LoginWidget(QWidget):
    def __init__(self, db, stacked):
        super().__init__()
        self.db = db
        self.stacked = stacked
        self.init_ui()

    def init_ui(self):
        container = QFrame()
        container.setObjectName("container")
        container.setFixedSize(450, 520)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        # Logo no topo
        logo_label = QLabel()
        pixmap = QPixmap("assets/logo.png")
        if not pixmap.isNull():
            pixmap = pixmap.scaledToWidth(120, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)

        title = QLabel("CallMe - Sistema de Chamados")
        title.setObjectName("title")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.email_field = QLineEdit()
        self.email_field.setPlaceholderText("Email corporativo")
        self.email_field.setFixedHeight(39)
        layout.addWidget(self.email_field)

        self.password_field = QLineEdit()
        self.password_field.setPlaceholderText("Senha")
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.setFixedHeight(39)
        layout.addWidget(self.password_field)

        self.re_field = QLineEdit()
        self.re_field.setPlaceholderText("RE (Registro Empresarial)")
        self.re_field.setFixedHeight(39)
        layout.addWidget(self.re_field)

        self.login_btn = QPushButton("Entrar")
        self.login_btn.setFixedHeight(35)
        layout.addWidget(self.login_btn)

        self.forgot_btn = QPushButton("Esqueci minha senha")
        self.forgot_btn.setFixedHeight(35)
        layout.addWidget(self.forgot_btn)

        self.register_btn = QPushButton("Crie sua conta")
        self.register_btn.setFixedHeight(35)
        layout.addWidget(self.register_btn)

        main_layout = QVBoxLayout(self)
        main_layout.addStretch()
        main_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()

        self.login_btn.clicked.connect(self.on_login)
        self.register_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(1))
        self.forgot_btn.clicked.connect(self.on_forgot_password)

    def on_login(self):
        email = self.email_field.text().strip()
        pw = self.password_field.text()
        reval = self.re_field.text().strip()
        user = self.db.find_user_by_email(email)
        if not user:
            QMessageBox.warning(self, "Erro", "Usuário não encontrado.")
            return
        if user['re'] != reval:
            QMessageBox.warning(self, "Erro", "RE não corresponde ao usuário.")
            return
        if user['password_hash'] != hash_password(pw):
            QMessageBox.warning(self, "Erro", "Senha incorreta.")
            return
        # chama MainWindow para abrir as telas
        if user['role'] == 'tecnico':
            self.stacked.parent().open_tech_home(user)
        else:
            self.stacked.parent().open_employee_home(user)

    def on_forgot_password(self):
        """Abre diálogo modal para recuperação de senha (email + RE + nova senha)."""
        dlg = PasswordRecoveryDialog(self.db, parent=self)
        dlg.exec()

# ----------------------- Diálogo de Recuperação de Senha -----------------------
class PasswordRecoveryDialog(QDialog):
    """
    Dialog único que pede: Email, RE, Nova senha, Confirmação.
    Valida e atualiza a senha no banco.
    """
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Recuperar senha")
        self.setFixedSize(420, 320)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel("Informe seu Email e RE para redefinir a senha")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email cadastrado")
        layout.addWidget(self.email_edit)

        self.re_edit = QLineEdit()
        self.re_edit.setPlaceholderText("RE (Registro Empresarial)")
        layout.addWidget(self.re_edit)

        self.new_pw = QLineEdit()
        self.new_pw.setPlaceholderText("Nova senha")
        self.new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_pw)

        self.confirm_pw = QLineEdit()
        self.confirm_pw.setPlaceholderText("Confirmar nova senha")
        self.confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.confirm_pw)

        btns = QHBoxLayout()
        btns.addStretch()
        self.cancel_btn = QPushButton("Cancelar")
        self.save_btn = QPushButton("Redefinir senha")
        self.cancel_btn.setFixedHeight(36)
        self.save_btn.setFixedHeight(36)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        layout.addLayout(btns)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.on_save)

    def on_save(self):
        email = self.email_edit.text().strip()
        reval = self.re_edit.text().strip()
        pw = self.new_pw.text()
        pw2 = self.confirm_pw.text()

        if not (email and reval and pw and pw2):
            QMessageBox.warning(self, "Erro", "Preencha todos os campos.")
            return

        if pw != pw2:
            QMessageBox.warning(self, "Erro", "As senhas não conferem.")
            return

        # verifica se existe usuário com email e RE
        user = self.db.find_user_by_email(email)
        if not user:
            QMessageBox.warning(self, "Erro", "Email não cadastrado.")
            return
        if user['re'] != reval:
            QMessageBox.warning(self, "Erro", "RE não corresponde ao usuário.")
            return

        # atualiza senha
        new_hash = hash_password(pw)
        ok = self.db.update_password_by_email_re(email, reval, new_hash)
        if ok:
            QMessageBox.information(self, "Sucesso", "Senha atualizada com sucesso.")
            self.accept()
        else:
            QMessageBox.critical(self, "Erro", "Falha ao atualizar senha. Verifique os dados e tente novamente.")

# ----------------------- Registro -----------------------
class RegisterWidget(QWidget):
    def __init__(self, db, stacked):
        super().__init__()
        self.db = db
        self.stacked = stacked
        self.init_ui()

    def init_ui(self):
        container = QFrame()
        container.setObjectName("container")
        container.setFixedSize(400, 490)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        title = QLabel("Criar Conta")
        title.setObjectName("title")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Nome completo")
        self.name_field.setFixedHeight(39)
        layout.addWidget(self.name_field)

        self.email_field = QLineEdit()
        self.email_field.setPlaceholderText("Email")
        self.email_field.setFixedHeight(39)
        layout.addWidget(self.email_field)

        self.password_field = QLineEdit()
        self.password_field.setPlaceholderText("Senha")
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.setFixedHeight(39)
        layout.addWidget(self.password_field)

        self.re_field = QLineEdit()
        self.re_field.setPlaceholderText("RE fornecido pela empresa")
        self.re_field.setFixedHeight(39)
        layout.addWidget(self.re_field)

        self.create_btn = QPushButton("Criar Conta")
        self.create_btn.setFixedHeight(35)
        layout.addWidget(self.create_btn)

        self.back_btn = QPushButton("Voltar")
        self.back_btn.setFixedHeight(35)
        layout.addWidget(self.back_btn)

        main_layout = QVBoxLayout(self)
        main_layout.addStretch()
        main_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()

        self.create_btn.clicked.connect(self.on_create)
        self.back_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(0))

    def on_create(self):
        name = self.name_field.text().strip()
        email = self.email_field.text().strip()
        pw = self.password_field.text()
        reval = self.re_field.text().strip()
        if not (name and email and pw and reval):
            QMessageBox.warning(self, "Erro", "Preencha todos os campos.")
            return
        re_row = self.db.check_re(reval)
        if not re_row:
            QMessageBox.warning(self, "Erro", "RE inválido.")
            return
        role = re_row['role']
        ok = self.db.create_user(name, email, hash_password(pw), role, reval)
        if not ok:
            QMessageBox.warning(self, "Erro", "Email já cadastrado.")
            return
        QMessageBox.information(self, "Sucesso", f"Conta criada como {role}.")
        self.stacked.setCurrentIndex(0)

# ----------------------- Ticket Form (centralizado e largo) -----------------------
class TicketForm(QWidget):
    def __init__(self, db, user, parent_home=None):
        super().__init__()
        self.db = db
        self.user = user
        self.parent_home = parent_home
        self.init_ui()

    def _apply_sizes(self):
        # Controles maiores e consistentes
        self.title_edit.setFixedHeight(44)
        self.desc_edit.setFixedHeight(180)
        self.send_btn.setFixedHeight(48)
        self.cancel_btn.setFixedHeight(48)
        self.send_btn.setMinimumWidth(180)
        self.cancel_btn.setMinimumWidth(140)
        self.send_btn.setObjectName("primary_btn")

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        form_wrap = QFrame()
        form_wrap.setObjectName("form_wrap")
        form_layout = QVBoxLayout(form_wrap)
        form_layout.setSpacing(16)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_wrap.setMaximumWidth(900)

        title = QLabel("Abrir Novo Chamado")
        title.setObjectName("content_title")
        form_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título do Chamado")

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Descrição detalhada do problema")

        form_layout.addWidget(self.title_edit)
        form_layout.addWidget(self.desc_edit)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btns.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.send_btn = QPushButton("Abrir Chamado")
        self.cancel_btn = QPushButton("Cancelar")
        btns.addWidget(self.send_btn)
        btns.addWidget(self.cancel_btn)
        form_layout.addLayout(btns)

        outer.addWidget(form_wrap, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

        self._apply_sizes()

        self.send_btn.clicked.connect(self.send)
        self.cancel_btn.clicked.connect(self.cancel)

    def send(self):
        title = self.title_edit.text().strip()
        desc = self.desc_edit.toPlainText().strip()
        if not (title and desc):
            QMessageBox.warning(self, "Erro", "Preencha todos os campos.")
            return
        self.db.create_ticket(title, desc, self.user['id'])
        QMessageBox.information(self, "Sucesso", "Chamado criado!")
        if self.parent_home:
            self.parent_home.load_tickets()
        self.title_edit.clear()
        self.desc_edit.clear()

    def cancel(self):
        self.title_edit.clear()
        self.desc_edit.clear()

# ----------------------- Profile Form (reutilizável) -----------------------
class ProfileForm(QWidget):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user
        self.init_ui()

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.addStretch()

        form_wrap = QFrame()
        form_wrap.setMaximumWidth(900)
        layout = QVBoxLayout(form_wrap)
        layout.setSpacing(12)
        layout.setContentsMargins(0,0,0,0)

        title = QLabel("Meu Perfil")
        title.setObjectName("content_title")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.name_edit = QLineEdit(self.user['name'])
        self.email_edit = QLineEdit(self.user['email'])
        self.re_label = QLabel(self.user['re'])
        self.role_label = QLabel(self.user['role'])

        lbl_name = QLabel("Nome:")
        lbl_name.setObjectName("form_label")
        layout.addWidget(lbl_name)
        layout.addWidget(self.name_edit)

        lbl_email = QLabel("Email:")
        lbl_email.setObjectName("form_label")
        layout.addWidget(lbl_email)
        layout.addWidget(self.email_edit)

        lbl_re = QLabel("RE:")
        lbl_re.setObjectName("form_label")
        layout.addWidget(lbl_re)
        layout.addWidget(self.re_label)

        lbl_role = QLabel("Função:")
        lbl_role.setObjectName("form_label")
        layout.addWidget(lbl_role)
        layout.addWidget(self.role_label)

        self.save_btn = QPushButton("Salvar Alterações")
        self.save_btn.setFixedHeight(48)
        self.save_btn.setMinimumWidth(200)
        self.save_btn.setObjectName("primary_btn")
        layout.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(form_wrap, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

        self.save_btn.clicked.connect(self.save_profile)

    def save_profile(self):
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        if not (name and email):
            QMessageBox.warning(self, "Erro", "Preencha todos os campos obrigatórios.")
            return
        self.db.update_user(self.user['id'], name, email)
        QMessageBox.information(self, "Sucesso", "Perfil atualizado!")
        # refresh local user data
        self.user = self.db.get_user_by_id(self.user['id'])

# ----------------------- Employee Home (refatorado painel) -----------------------
class EmployeeHome(QWidget):
    def __init__(self, db, stacked, user):
        super().__init__()
        self.db = db
        self.stacked = stacked
        self.user = user
        self.init_ui()
        self.load_tickets()

    def _style_table(self):
        table_font = QFont()
        table_font.setPointSize(12)
        self.ticket_table.setFont(table_font)
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        self.ticket_table.horizontalHeader().setFont(header_font)
        self.ticket_table.verticalHeader().setVisible(False)
        self.ticket_table.setShowGrid(False)
        self.ticket_table.setAlternatingRowColors(True)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20,20,20,20)
        root.setSpacing(15)

        top = QHBoxLayout()
        logo_label = QLabel()
        pixmap = QPixmap("assets/logo.png").scaledToWidth(150, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(pixmap)
        top.addWidget(logo_label)
        top.addStretch()
        self.logout_btn = QPushButton("Sair")
        self.logout_btn.setFixedHeight(36)
        self.logout_btn.setFixedWidth(110)
        top.addWidget(self.logout_btn)
        root.addLayout(top)
        self.logout_btn.clicked.connect(self.logout)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24,24,24,24)
        panel_layout.setSpacing(16)
        root.addWidget(panel)

        # welcome as attribute to allow updates after profile change
        self.welcome_label = QLabel(f"Bem-vindo, {self.user['name']}!")
        self.welcome_label.setStyleSheet("font-size:25px; font-weight:bold; color:#333;")
        self.welcome_label.setObjectName("welcome_label")
        panel_layout.addWidget(self.welcome_label)

        self.tabs = QTabWidget()
        panel_layout.addWidget(self.tabs)

        # Meus Chamados (Employee) - includes description preview and clickable dialog
        self.tickets_tab = QWidget()
        tickets_layout = QVBoxLayout(self.tickets_tab)
        self.ticket_table = QTableWidget()
        # Columns: ID, Title, Description (preview), Status (read-only), Date
        self.ticket_table.setColumnCount(5)
        self.ticket_table.setHorizontalHeaderLabels(["ID","Título","Descrição","Status","Data"])
        self.ticket_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tickets_layout.addWidget(self.ticket_table)

        # Add export buttons for employee view (CSV + PDF for their tickets)
        btn_row = QHBoxLayout()
        self.export_csv_btn_emp = QPushButton("Exportar CSV")
        self.export_pdf_btn_emp = QPushButton("Exportar PDF")
        for b in (self.export_csv_btn_emp, self.export_pdf_btn_emp):
            b.setFixedHeight(36)
            b.setMinimumWidth(140)
        btn_row.addWidget(self.export_csv_btn_emp)
        btn_row.addWidget(self.export_pdf_btn_emp)
        btn_row.addStretch()
        tickets_layout.addLayout(btn_row)

        self.tabs.addTab(self.tickets_tab, "Meus Chamados")
        self._style_table()

        # Abrir Chamado
        self.open_tab = QWidget()
        open_layout = QVBoxLayout(self.open_tab)
        self.ticket_form = TicketForm(self.db, self.user, self)
        open_layout.addWidget(self.ticket_form)
        self.tabs.addTab(self.open_tab, "Abrir Chamado")

        # Perfil
        self.profile_tab = QWidget()
        profile_layout = QVBoxLayout(self.profile_tab)
        self.profile_form = ProfileForm(self.db, self.user)
        profile_layout.addWidget(self.profile_form)
        self.tabs.addTab(self.profile_tab, "Perfil")

        # Connect profile save to update welcome label and local user
        self.profile_form.save_btn.clicked.connect(self.on_profile_saved)

        # connect cell click to show full description
        self.ticket_table.cellClicked.connect(self.on_cell_clicked)

        # connect export buttons
        self.export_csv_btn_emp.clicked.connect(self.export_csv_emp)
        self.export_pdf_btn_emp.clicked.connect(self.export_pdf_emp)

    def on_profile_saved(self):
        # refresh user and update welcome label
        self.user = self.db.get_user_by_id(self.user['id'])
        self.profile_form.user = self.user
        self.welcome_label.setText(f"Bem-vindo, {self.user['name']}!")
        self.welcome_label.setStyleSheet("font-size:25px; font-weight:bold; color:#333;")
        self.load_tickets()

    def load_tickets(self):
        # Mapeamento de cores para cada status
        status_colors = {
            'Aberto': '#FF0000',           # Vermelho
            'Aguardando Técnico': '#FFA500',  # Amarelo
            'Em Atendimento': '#0055FF',   # Azul
            'Finalizado': '#008000'        # Verde
        }
        
        tickets = self.db.get_tickets_for_user(self.user)
        self.ticket_table.setRowCount(0)
        for t in tickets:
            row = self.ticket_table.rowCount()
            self.ticket_table.insertRow(row)
            # ID
            self.ticket_table.setItem(row,0,QTableWidgetItem(str(t['id'])))
            # Title
            self.ticket_table.setItem(row,1,QTableWidgetItem(t['title']))
            # Description preview
            desc_preview = t['description'][:120] + ("..." if len(t['description'])>120 else "")
            item_desc = QTableWidgetItem(desc_preview)
            item_desc.setData(Qt.ItemDataRole.UserRole, t['description'])
            # make item not editable
            item_desc.setFlags(item_desc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.ticket_table.setItem(row,2,item_desc)
            # Status (read-only for employees)
            status_item = QTableWidgetItem(t['status'])
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Aplicar cor com base no status
            status_color = status_colors.get(t['status'], '#000000')  # Preto padrão se status não mapeado
            status_item.setForeground(QColor(status_color))
            self.ticket_table.setItem(row,3,status_item)
            # Created at
            self.ticket_table.setItem(row,4,QTableWidgetItem(t['created_at']))

    def on_cell_clicked(self, row, column):
        # if description column clicked, open a dialog with full text
        if column == 2:
            item = self.ticket_table.item(row, column)
            if not item:
                return
            full_text = item.data(Qt.ItemDataRole.UserRole) or item.text()
            dlg = QDialog(self)
            dlg.setWindowTitle('Descrição completa')
            dlg.setFixedSize(700, 420)
            layout = QVBoxLayout(dlg)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setPlainText(full_text)
            layout.addWidget(txt)
            btn = QPushButton('Fechar')
            btn.setFixedHeight(32)
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
            dlg.exec()

    def export_csv_emp(self):
        path,_ = QFileDialog.getSaveFileName(self, "Salvar CSV","my_tickets.csv","CSV Files (*.csv)")
        if path:
            self.db.export_tickets_csv(path, user_id=self.user['id'])
            QMessageBox.information(self, "Sucesso","Seus tickets foram exportados em CSV.")

    def export_pdf_emp(self):
        path,_ = QFileDialog.getSaveFileName(self, "Salvar PDF","my_tickets.pdf","PDF Files (*.pdf)")
        if path:
            try:
                self.db.export_tickets_pdf(path, user_id=self.user['id'])
                QMessageBox.information(self, "Sucesso","Seus tickets foram exportados em PDF.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF: {e}")

    def logout(self):
        # Mostrar diálogo de confirmação antes de sair
        if ConfirmDialog.ask(self, "Deseja realmente sair do sistema?"):
            self.stacked.setCurrentIndex(0)

# ----------------------- Tech Home (com filtro e perfil no topo) -----------------------
class TechHome(QWidget):
    STATUS_OPTIONS = ["Aberto","Aguardando Técnico","Em Atendimento","Finalizado"]

    def __init__(self, db, stacked, user):
        super().__init__()
        self.db = db
        self.stacked = stacked
        self.user = user
        self.current_filter = "Todos"
        self.init_ui()
        self.load_tickets()

    def _style_table(self):
        table_font = QFont()
        table_font.setPointSize(12)
        self.ticket_table.setFont(table_font)
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        self.ticket_table.horizontalHeader().setFont(header_font)
        self.ticket_table.verticalHeader().setVisible(False)
        self.ticket_table.setShowGrid(False)
        self.ticket_table.setAlternatingRowColors(True)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20,20,20,20)

        # Topo com logo + botões
        top_layout = QHBoxLayout()

        logo_label = QLabel()
        pixmap = QPixmap("assets/logo.png").scaledToWidth(150, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(pixmap)
        top_layout.addWidget(logo_label)

        self.chamados_btn = QPushButton("Chamados")
        self.perfil_btn = QPushButton("Meu Perfil")
        self.logout_btn = QPushButton("Sair")
        self.logout_btn.setFixedWidth(100)
        # style sizes
        for b in (self.chamados_btn, self.perfil_btn, self.logout_btn):
            b.setFixedHeight(36)

        top_layout.addWidget(self.chamados_btn)
        top_layout.addWidget(self.perfil_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.logout_btn)
        main_layout.addLayout(top_layout)

        self.chamados_btn.clicked.connect(self.show_chamados)
        self.perfil_btn.clicked.connect(self.show_perfil)
        self.logout_btn.clicked.connect(self.logout)

        # Stack interno: Chamados e Perfil
        self.inner_stack = QStackedWidget()
        main_layout.addWidget(self.inner_stack)

        # Chamados view
        self.chamados_widget = QWidget()
        chamados_layout = QVBoxLayout(self.chamados_widget)

        self.welcome_label = QLabel(f"Bem-vindo, {self.user['name']}!")
        self.welcome_label.setStyleSheet("font-size:25px; font-weight:bold; color:#333;")
        chamados_layout.addWidget(self.welcome_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # filtro
        filter_layout = QHBoxLayout()
        lbl_filter = QLabel("Filtrar por status:")
        lbl_filter.setFixedWidth(120)
        filter_layout.addWidget(lbl_filter)
        self.filter_box = QComboBox()
        self.filter_box.addItems(["Todos"] + self.STATUS_OPTIONS)
        self.filter_box.setFixedHeight(34)
        self.filter_box.setMinimumWidth(200)
        filter_layout.addWidget(self.filter_box)
        filter_layout.addStretch()
        chamados_layout.addLayout(filter_layout)

        self.filter_box.currentTextChanged.connect(self.apply_filter)

        # tabela
        self.ticket_table = QTableWidget()
        # corrected column count to match headers
        self.ticket_table.setColumnCount(7)
        self.ticket_table.setHorizontalHeaderLabels(["ID","Título","Descrição","Status","Criado por","Data","Resolução"])
        self.ticket_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        chamados_layout.addWidget(self.ticket_table)
        self._style_table()

        # botoes (added PDF button next to CSV)
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Atualizar")
        self.export_btn = QPushButton("Exportar CSV")
        self.export_pdf_btn = QPushButton("Exportar PDF")
        for b in (self.refresh_btn, self.export_btn, self.export_pdf_btn):
            b.setFixedHeight(40)
            b.setMinimumWidth(140)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.export_pdf_btn)
        btn_layout.addStretch()
        chamados_layout.addLayout(btn_layout)

        self.refresh_btn.clicked.connect(self.load_tickets)
        self.export_btn.clicked.connect(self.export_csv)
        self.export_pdf_btn.clicked.connect(self.export_pdf)

        # NOTE: removed double-click edit; instead: inline status combobox and clickable description
        self.ticket_table.cellClicked.connect(self.on_cell_clicked)

        self.inner_stack.addWidget(self.chamados_widget)

        # Perfil view (reutiliza ProfileForm)
        self.perfil_widget = ProfileForm(self.db, self.user)
        # conectar o save do perfil para atualizar nome/welcome e local user
        self.perfil_widget.save_btn.clicked.connect(self.on_profile_saved)

        self.inner_stack.addWidget(self.perfil_widget)

        self.inner_stack.setCurrentWidget(self.chamados_widget)

    def show_chamados(self):
        self.inner_stack.setCurrentWidget(self.chamados_widget)
        self.load_tickets()

    def show_perfil(self):
        self.inner_stack.setCurrentWidget(self.perfil_widget)

    def apply_filter(self, status):
        self.current_filter = status
        self.load_tickets()

    def load_tickets(self):
        # Mapeamento de cores para cada status
        status_colors = {
            'Aberto': '#FF0000',           # Vermelho
            'Aguardando Técnico': '#FFA500',  # Amarelo
            'Em Atendimento': '#0055FF',   # Azul
            'Finalizado': '#008000'        # Verde
        }
        
        tickets = self.db.get_tickets_for_user(self.user, self.current_filter)
        self.ticket_table.setRowCount(0)
        for t in tickets:
            row = self.ticket_table.rowCount()
            self.ticket_table.insertRow(row)
            # ID
            self.ticket_table.setItem(row,0,QTableWidgetItem(str(t['id'])))
            # Title
            self.ticket_table.setItem(row,1,QTableWidgetItem(t['title']))
            # Description (short preview)
            desc_preview = t['description'][:120] + ("..." if len(t['description'])>120 else "")
            item_desc = QTableWidgetItem(desc_preview)
            item_desc.setData(Qt.ItemDataRole.UserRole, t['description'])  # store full text on item
            self.ticket_table.setItem(row,2,item_desc)
            # Status: insert combobox widget
            status_combo = QComboBox()
            status_combo.addItems(self.STATUS_OPTIONS)
            status_combo.setCurrentText(t['status'])
            # Aplicar cor ao QComboBox
            status_color = status_colors.get(t['status'], '#000000')  # Preto padrão
            status_combo.setStyleSheet(f"color: {status_color};")
            # store ticket id on combo for callback
            status_combo.tid = t['id']
            status_combo.currentTextChanged.connect(lambda s, combo=status_combo: self.on_status_changed(combo.tid, s))
            self.ticket_table.setCellWidget(row,3,status_combo)
            # Creator
            self.ticket_table.setItem(row,4,QTableWidgetItem(t['creator_name']))
            # Created at
            self.ticket_table.setItem(row,5,QTableWidgetItem(t['created_at']))
            # Resolution
            self.ticket_table.setItem(row,6,QTableWidgetItem(t['resolution'] or ""))

    def on_status_changed(self, tid, status):
        # when user marks as Finalizado, ask for resolution text
        resolution = None
        if status == 'Finalizado':
            dlg = QDialog(self)
            dlg.setWindowTitle('Observações / Resolução')
            dlg.setFixedSize(600, 360)
            layout = QVBoxLayout(dlg)
            lbl = QLabel('Informe as observações / resolução (visível para o usuário):')
            layout.addWidget(lbl)
            txt = QTextEdit()
            txt.setPlaceholderText('Descreva a resolução...')
            layout.addWidget(txt)
            btns = QHBoxLayout()
            btns.addStretch()
            ok = QPushButton('Salvar')
            cancel = QPushButton('Cancelar')
            ok.setFixedHeight(36)
            cancel.setFixedHeight(36)
            btns.addWidget(cancel)
            btns.addWidget(ok)
            layout.addLayout(btns)

            def on_ok():
                nonlocal resolution
                resolution = txt.toPlainText().strip()
                dlg.accept()

            def on_cancel():
                dlg.reject()

            ok.clicked.connect(on_ok)
            cancel.clicked.connect(on_cancel)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                # user cancelled: reload tickets to reset combo to previous value
                self.load_tickets()
                return

        # persist to DB
        self.db.update_ticket_status(tid, status, resolution)
        QMessageBox.information(self, 'Sucesso', f'Status do chamado {tid} atualizado para "{status}".')
        self.load_tickets()

    def on_cell_clicked(self, row, column):
        # if description column clicked, open a dialog with full text
        if column == 2:
            item = self.ticket_table.item(row, column)
            if not item:
                return
            full_text = item.data(Qt.ItemDataRole.UserRole) or item.text()
            dlg = QDialog(self)
            dlg.setWindowTitle('Descrição completa')
            dlg.setFixedSize(700, 420)
            layout = QVBoxLayout(dlg)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setPlainText(full_text)
            layout.addWidget(txt)
            btn = QPushButton('Fechar')
            btn.setFixedHeight(32)
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
            dlg.exec()

    def export_csv(self):
        path,_ = QFileDialog.getSaveFileName(self, "Salvar CSV","tickets.csv","CSV Files (*.csv)")
        if path:
            self.db.export_tickets_csv(path)
            QMessageBox.information(self, "Sucesso","Tickets exportados.")

    def export_pdf(self):
        path,_ = QFileDialog.getSaveFileName(self, "Salvar PDF","tickets.pdf","PDF Files (*.pdf)")
        if path:
            try:
                self.db.export_tickets_pdf(path)
                QMessageBox.information(self, "Sucesso","Tickets exportados em PDF.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF: {e}")

    def on_profile_saved(self):
        # refresh user and update welcome labels
        self.user = self.db.get_user_by_id(self.user['id'])
        self.perfil_widget.user = self.user
        self.welcome_label.setText(f"Bem-vindo, {self.user['name']}!")
        self.welcome_label.setStyleSheet("font-size:25px; font-weight:bold; color:#333;")
        # also update employee welcome if needed elsewhere by reloading
        self.load_tickets()

    def logout(self):
        # Mostrar diálogo de confirmação antes de sair
        if ConfirmDialog.ask(self, "Deseja realmente sair do sistema?"):
            self.stacked.setCurrentIndex(0)

# ----------------------- Main Window (aplica estilos) -----------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CallMe - Sistema de Chamados")
        self.resize(1200, 820)

        # Ícone da aplicação
        self.setWindowIcon(QIcon("assets/logowindow.png"))

        self.db = Database()
        self.stacked = QStackedWidget()
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.stacked)

        # Widgets
        self.login_widget = LoginWidget(self.db, self.stacked)
        self.register_widget = RegisterWidget(self.db, self.stacked)
        self.stacked.addWidget(self.login_widget)
        self.stacked.addWidget(self.register_widget)

        self.apply_styles()

    def apply_styles(self):
        style = """
        QFrame#container {
            background-color: #ffffff;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #cccccc;
        }

        QLabel#title {
            font-size: 26px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333333;
        }

        QLabel#content_title {
            font-size: 30px;
            font-weight: bold;
            margin: 8px 0 18px 0;
            color: #0055ff;
        }

        QFrame#panel {
            background-color: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
        }

        QLabel#welcome_label {
            font-size: 20px;
            font-weight: 700;
            color: #333333;
            margin-bottom: 6px;
        }

        QFrame#panel QLineEdit,
        QFrame#panel QTextEdit,
        QLineEdit, QTextEdit {
            border: 1px solid #cccccc;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 16px;
            background-color: #fdfdfd;
        }
        QFrame#panel QLineEdit:focus,
        QFrame#panel QTextEdit:focus,
        QLineEdit:focus,
        QTextEdit:focus {
            border: 1px solid #0055ff;
        }

        QLabel#form_label {
            font-size: 16px;
            color: #555555;
            margin-top: 6px;
            margin-bottom: 4px;
        }

        QPushButton {
            background-color: #0055ff;
            color: white;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #003bb5;
        }
        QPushButton:pressed {
            background-color: #002080;
        }

        QPushButton#primary_btn {
            font-size: 16px;
            padding: 10px 18px;
        }

        QFrame#panel QTableWidget {
            font-size: 14px;
        }

        /* small niceties */
        QTabBar::tab { padding: 8px 18px; font-size: 14px; }
        QTabBar::tab:selected { font-weight: 600; }
        """
        self.setStyleSheet(style)

    def open_employee_home(self, user):
        home = EmployeeHome(self.db, self.stacked, user)
        if self.stacked.count()>2:
            self.stacked.removeWidget(self.stacked.widget(2))
        self.stacked.addWidget(home)
        self.stacked.setCurrentIndex(2)

    def open_tech_home(self, user):
        home = TechHome(self.db, self.stacked, user)
        if self.stacked.count()>2:
            self.stacked.removeWidget(self.stacked.widget(2))
        self.stacked.addWidget(home)
        self.stacked.setCurrentIndex(2)

# ----------------------- Main -----------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())