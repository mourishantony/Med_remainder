import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
import threading
import time
import json
from dotenv import load_dotenv
load_dotenv()
import os
import sys
import smtplib
from pymongo import MongoClient
from bson.objectid import ObjectId
from email.mime.text import MIMEText

# ─────────────────────────────────────────────
#  Settings Manager  (persists to settings.json)
# ─────────────────────────────────────────────
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')

_DEFAULT_SETTINGS = {
    "email_address":    os.getenv("EMAIL_ADDRESS", ""),
    "email_password":   os.getenv("EMAIL_PASSWORD", ""),
    "recipient_email":  os.getenv("RECIPIENT_EMAIL", ""),
    "twilio_account_sid":  os.getenv("TWILIO_ACCOUNT_SID", ""),
    "twilio_auth_token":   os.getenv("TWILIO_AUTH_TOKEN", ""),
    "twilio_from_number":  os.getenv("TWILIO_FROM_NUMBER", ""),
    "twilio_to_number":    os.getenv("TWILIO_TO_NUMBER", ""),
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
            merged = dict(_DEFAULT_SETTINGS)
            merged.update(saved)
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_SETTINGS)

def save_settings(settings: dict):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# Live settings dict – everything reads from here at runtime
APP_SETTINGS = load_settings()

def get_email_config():
    return {
        "smtp_server":    "smtp.gmail.com",
        "smtp_port":      587,
        "email_address":  APP_SETTINGS.get("email_address", ""),
        "email_password": APP_SETTINGS.get("email_password", ""),
        "recipient_email":APP_SETTINGS.get("recipient_email", ""),
    }

def get_twilio_config():
    return {
        "account_sid":  APP_SETTINGS.get("twilio_account_sid", ""),
        "auth_token":   APP_SETTINGS.get("twilio_auth_token", ""),
        "from_number":  APP_SETTINGS.get("twilio_from_number", ""),
        "to_number":    APP_SETTINGS.get("twilio_to_number", ""),
    }

# ─────────────────────────────────────────────
#  Feature flags
# ─────────────────────────────────────────────
EMAIL_ENABLED = True

TWILIO_ENABLED = True
try:
    from twilio.rest import Client
except ImportError:
    TWILIO_ENABLED = False

# ─────────────────────────────────────────────
#  Notification helpers
# ─────────────────────────────────────────────
def make_call(message):
    if not TWILIO_ENABLED:
        return
    cfg = get_twilio_config()
    if not cfg["account_sid"] or not cfg["auth_token"]:
        print("Twilio credentials not configured.")
        return
    try:
        client = Client(cfg["account_sid"], cfg["auth_token"])
        call = client.calls.create(
            to=cfg["to_number"],
            from_=cfg["from_number"],
            twiml=f'<Response><Say>{message}</Say></Response>'
        )
        print("Twilio call initiated. SID:", call.sid)
    except Exception as e:
        print("Failed to make Twilio call:", e)

try:
    import pygame
    SOUND_ENABLED = True
except ImportError:
    SOUND_ENABLED = False

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_ENABLED = True
except ImportError:
    TRAY_ENABLED = False


def play_sound():
    if SOUND_ENABLED:
        try:
            sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alarm.mp3')
            pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
        except Exception as e:
            print("Sound error:", e)

def send_email(subject, body):
    if not EMAIL_ENABLED:
        return
    cfg = get_email_config()
    if not cfg["email_address"] or not cfg["email_password"]:
        print("Email credentials not configured.")
        return
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = cfg["email_address"]
        msg['To'] = cfg["recipient_email"]
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["email_address"], cfg["email_password"])
            server.send_message(msg)
        print("Email sent successfully!")
    except Exception as e:
        print("Failed to send email:", e)

def show_tray_notification(title, msg):
    if TRAY_ENABLED and sys.platform.startswith('win'):
        def create_image():
            image = Image.new('RGB', (64, 64), color=(0, 64, 128))
            d = ImageDraw.Draw(image)
            d.ellipse((16, 16, 48, 48), fill=(255, 255, 0))
            return image
        image = create_image()
        icon = pystray.Icon("reminder", image, title, menu=None)
        icon.visible = True
        icon.notify(msg)
        icon.stop()

# ─────────────────────────────────────────────
#  Settings Dialog
# ─────────────────────────────────────────────
class SettingsDialog:
    """
    A modal settings window with two tabs:
      • Email – SMTP sender address, app password, recipient
      • Twilio – Account SID, Auth Token, from/to numbers
    Values are saved to settings.json and applied immediately.
    """

    COLORS = {
        'bg':          '#1e2433',
        'panel':       '#252d3d',
        'accent':      '#3b82f6',
        'accent_dark': '#2563eb',
        'success':     '#10b981',
        'danger':      '#ef4444',
        'text':        '#f1f5f9',
        'muted':       '#94a3b8',
        'input_bg':    '#2d3748',
        'border':      '#374151',
        'tab_active':  '#3b82f6',
        'tab_inactive':'#374151',
    }

    def __init__(self, parent):
        self.parent = parent
        self.result = None

        self.dialog = tk.Toplevel(parent.root)
        self.dialog.title("⚙️  Settings")
        self.dialog.geometry("560x580")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg=self.COLORS['bg'])
        self.dialog.transient(parent.root)
        self.dialog.grab_set()

        # Centre
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth()  // 2) - (560 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (580 // 2)
        self.dialog.geometry(f"560x580+{x}+{y}")

        self._build_ui()
        self._populate()

    # ── UI construction ────────────────────────────────────────────────
    def _build_ui(self):
        C = self.COLORS

        # ── Header bar ──────────────────────────────────────────────────
        header = tk.Frame(self.dialog, bg=C['accent'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)

        tk.Label(header, text="⚙️  Settings", font=('Segoe UI', 16, 'bold'),
                 bg=C['accent'], fg='white').pack(side='left', padx=24, pady=15)
        tk.Label(header, text="Configure notifications & credentials",
                 font=('Segoe UI', 10), bg=C['accent'], fg='#dbeafe').pack(
                 side='left', padx=0, pady=15)

        # ── Tab strip ────────────────────────────────────────────────────
        tab_bar = tk.Frame(self.dialog, bg=C['panel'], height=44)
        tab_bar.pack(fill='x')
        tab_bar.pack_propagate(False)

        self.content_area = tk.Frame(self.dialog, bg=C['bg'])
        self.content_area.pack(fill='both', expand=True)

        self._tabs = {}        # name -> frame
        self._tab_btns = {}    # name -> button
        self._active_tab = tk.StringVar(value='email')

        for name, label in [('email', '📧  Email'), ('twilio', '📞  Twilio')]:
            btn = tk.Button(
                tab_bar, text=label,
                font=('Segoe UI', 10, 'bold'),
                fg='white', relief='flat', padx=22, pady=10,
                command=lambda n=name: self._switch_tab(n)
            )
            btn.pack(side='left')
            self._tab_btns[name] = btn

            frame = tk.Frame(self.content_area, bg=C['bg'], padx=30, pady=20)
            self._tabs[name] = frame

        # ── Email tab contents ──────────────────────────────────────────
        self._email_vars = {}
        email_fields = [
            ('email_address',   '📧  Sender Email Address',
             'e.g. yourname@gmail.com',  False),
            ('email_password',  '🔑  Email App Password',
             'Gmail app password (16 chars)', True),
            ('recipient_email', '📨  Recipient Email Address',
             'Who receives the alerts',   False),
        ]
        self._build_field_group(self._tabs['email'], email_fields, self._email_vars)

        # info note
        note = tk.Frame(self._tabs['email'], bg='#1a2744', pady=8, padx=12)
        note.pack(fill='x', pady=(0, 10))
        tk.Label(note,
                 text="ℹ️  For Gmail, enable 2-Step Verification and generate an App Password\n"
                      "    at myaccount.google.com → Security → App passwords.",
                 font=('Segoe UI', 8), bg='#1a2744', fg='#93c5fd',
                 justify='left').pack(anchor='w')

        # ── Twilio tab contents ─────────────────────────────────────────
        self._twilio_vars = {}
        twilio_fields = [
            ('twilio_account_sid',  '🆔  Account SID',
             'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', False),
            ('twilio_auth_token',   '🔐  Auth Token',
             'Your Twilio auth token',            True),
            ('twilio_from_number',  '📲  From Number',
             '+1XXXXXXXXXX  (Twilio number)',     False),
            ('twilio_to_number',    '📱  To Number',
             '+91XXXXXXXXXX  (your mobile)',       False),
        ]
        self._build_field_group(self._tabs['twilio'], twilio_fields, self._twilio_vars)

        # ── Bottom action bar ─────────────────────────────────────────────
        action_bar = tk.Frame(self.dialog, bg=C['panel'], height=64)
        action_bar.pack(fill='x', side='bottom')
        action_bar.pack_propagate(False)

        # Test buttons
        tk.Button(action_bar, text="✉️ Test Email",
                  font=('Segoe UI', 9, 'bold'),
                  bg='#0f766e', fg='white', relief='flat', padx=14, pady=8,
                  command=self._test_email).pack(side='left', padx=(16, 6), pady=12)

        tk.Button(action_bar, text="📞 Test Call",
                  font=('Segoe UI', 9, 'bold'),
                  bg='#6d28d9', fg='white', relief='flat', padx=14, pady=8,
                  command=self._test_call).pack(side='left', padx=6, pady=12)

        # Cancel / Save
        tk.Button(action_bar, text="Cancel",
                  font=('Segoe UI', 10),
                  bg=C['border'], fg=C['text'], relief='flat', padx=18, pady=8,
                  command=self.dialog.destroy).pack(side='right', padx=(6, 16), pady=12)

        tk.Button(action_bar, text="💾  Save Settings",
                  font=('Segoe UI', 10, 'bold'),
                  bg=C['accent'], fg='white', relief='flat', padx=18, pady=8,
                  command=self._save).pack(side='right', padx=6, pady=12)

        # Show email tab by default
        self._switch_tab('email')

    def _build_field_group(self, parent, fields, var_dict):
        """Render a list of labelled entry rows into *parent*."""
        C = self.COLORS
        for key, label, placeholder, is_secret in fields:
            row = tk.Frame(parent, bg=C['bg'])
            row.pack(fill='x', pady=(0, 14))

            tk.Label(row, text=label, font=('Segoe UI', 9, 'bold'),
                     bg=C['bg'], fg=C['muted']).pack(anchor='w', pady=(0, 4))

            var = tk.StringVar()
            var_dict[key] = var

            show = '*' if is_secret else ''
            entry = tk.Entry(row, textvariable=var,
                             font=('Segoe UI', 11),
                             bg=C['input_bg'], fg=C['text'],
                             insertbackground=C['text'],
                             relief='flat', show=show,
                             highlightthickness=1,
                             highlightbackground=C['border'],
                             highlightcolor=C['accent'])
            entry.pack(fill='x', ipady=7)

            # Placeholder logic
            if placeholder:
                entry.insert(0, placeholder)
                entry.config(fg=C['muted'])

                def _focus_in(e, w=entry, ph=placeholder, v=var):
                    if w.get() == ph:
                        w.delete(0, tk.END)
                        w.config(fg=self.COLORS['text'])

                def _focus_out(e, w=entry, ph=placeholder, v=var):
                    if w.get() == '':
                        w.insert(0, ph)
                        w.config(fg=self.COLORS['muted'])

                entry.bind('<FocusIn>',  _focus_in)
                entry.bind('<FocusOut>', _focus_out)

    def _switch_tab(self, name):
        C = self.COLORS
        for n, frame in self._tabs.items():
            frame.pack_forget()
        for n, btn in self._tab_btns.items():
            btn.config(bg=C['tab_active'] if n == name else C['tab_inactive'])
        self._tabs[name].pack(fill='both', expand=True)
        self._active_tab.set(name)

    # ── Populate from current APP_SETTINGS ────────────────────────────
    def _populate(self):
        placeholders = {
            'email_address':       'e.g. yourname@gmail.com',
            'email_password':      'Gmail app password (16 chars)',
            'recipient_email':     'Who receives the alerts',
            'twilio_account_sid':  'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'twilio_auth_token':   'Your Twilio auth token',
            'twilio_from_number':  '+1XXXXXXXXXX  (Twilio number)',
            'twilio_to_number':    '+91XXXXXXXXXX  (your mobile)',
        }
        all_vars = {**self._email_vars, **self._twilio_vars}
        for key, var in all_vars.items():
            val = APP_SETTINGS.get(key, '')
            if val:
                var.set(val)
                # Restore text colour for real values
                # (the entry widget fg was set grey for placeholder)
            else:
                var.set(placeholders.get(key, ''))

    # ── Save ──────────────────────────────────────────────────────────
    def _save(self):
        placeholders = {
            'email_address':       'e.g. yourname@gmail.com',
            'email_password':      'Gmail app password (16 chars)',
            'recipient_email':     'Who receives the alerts',
            'twilio_account_sid':  'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'twilio_auth_token':   'Your Twilio auth token',
            'twilio_from_number':  '+1XXXXXXXXXX  (Twilio number)',
            'twilio_to_number':    '+91XXXXXXXXXX  (your mobile)',
        }
        new_settings = {}
        all_vars = {**self._email_vars, **self._twilio_vars}
        for key, var in all_vars.items():
            val = var.get().strip()
            if val == placeholders.get(key, ''):
                val = ''   # treat placeholder text as empty
            new_settings[key] = val

        # Persist to file & update live dict
        save_settings(new_settings)
        APP_SETTINGS.update(new_settings)

        messagebox.showinfo("Settings Saved",
                            "✅ Settings saved successfully!\n"
                            "Email & Twilio will use the new values immediately.",
                            parent=self.dialog)
        self.dialog.destroy()

    # ── Test helpers ─────────────────────────────────────────────────
    def _test_email(self):
        # Temporarily apply form values
        self._apply_temp()
        try:
            send_email("🔔 Medicine Reminder – Test",
                       "This is a test email from your Medicine Reminder app.")
            messagebox.showinfo("Test Email",
                                "✅ Test email sent!\nCheck your inbox.",
                                parent=self.dialog)
        except Exception as e:
            messagebox.showerror("Test Email Failed",
                                 f"❌ Could not send email:\n{e}",
                                 parent=self.dialog)

    def _test_call(self):
        self._apply_temp()
        try:
            make_call("This is a test call from your Medicine Reminder app.")
            messagebox.showinfo("Test Call",
                                "✅ Test call initiated via Twilio!",
                                parent=self.dialog)
        except Exception as e:
            messagebox.showerror("Test Call Failed",
                                 f"❌ Could not make call:\n{e}",
                                 parent=self.dialog)

    def _apply_temp(self):
        """Push form values into APP_SETTINGS temporarily for testing."""
        placeholders = {
            'email_address':       'e.g. yourname@gmail.com',
            'email_password':      'Gmail app password (16 chars)',
            'recipient_email':     'Who receives the alerts',
            'twilio_account_sid':  'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'twilio_auth_token':   'Your Twilio auth token',
            'twilio_from_number':  '+1XXXXXXXXXX  (Twilio number)',
            'twilio_to_number':    '+91XXXXXXXXXX  (your mobile)',
        }
        all_vars = {**self._email_vars, **self._twilio_vars}
        for key, var in all_vars.items():
            val = var.get().strip()
            if val == placeholders.get(key, ''):
                val = ''
            APP_SETTINGS[key] = val


# ─────────────────────────────────────────────
#  Database
# ─────────────────────────────────────────────
class ReminderDatabase:
    def __init__(self, db_url='mongodb://localhost:27017/', db_name='reminder_db', collection_name='reminders'):
        self.client = MongoClient(db_url)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def add_reminder(self, reminder):
        reminder['notified'] = bool(reminder['notified'])
        reminder['taken'] = bool(reminder['taken'])
        reminder['enabled'] = bool(reminder.get('enabled', True))
        self.collection.insert_one(reminder)

    def update_reminder(self, idx, reminder):
        reminder['notified'] = bool(reminder['notified'])
        reminder['taken'] = bool(reminder['taken'])
        reminder['enabled'] = bool(reminder.get('enabled', True))
        self.collection.update_one(
            {'_id': ObjectId(idx)},
            {'$set': reminder}
        )

    def delete_reminder(self, idx):
        self.collection.delete_one({'_id': ObjectId(idx)})

    def get_reminders(self):
        result = []
        for doc in self.collection.find():
            reminder = doc.copy()
            reminder['id'] = str(doc['_id'])
            del reminder['_id']
            result.append(reminder)
        return result

    def get_reminder_by_id(self, idx):
        doc = self.collection.find_one({'_id': ObjectId(idx)})
        if doc:
            reminder = doc.copy()
            reminder['id'] = str(doc['_id'])
            del reminder['_id']
            return reminder
        return None

    def close(self):
        self.client.close()

# ─────────────────────────────────────────────
#  Add / Edit Reminder Dialog
# ─────────────────────────────────────────────
class ModernReminderDialog:
    def __init__(self, parent, reminder=None):
        self.parent = parent
        self.reminder = reminder
        self.result = None
        
        self.dialog = tk.Toplevel(parent.root)
        self.dialog.title("Add New Reminder" if reminder is None else "Edit Reminder")
        self.dialog.geometry("450x500")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg='#f8f9fa')
        self.dialog.transient(parent.root)
        self.dialog.grab_set()
        
        # Center the dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (500 // 2)
        self.dialog.geometry(f"450x500+{x}+{y}")
        
        self.create_widgets()
        
        if reminder:
            self.populate_fields()
    
    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.dialog, bg='#f8f9fa', padx=30, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_text = "Add New Reminder" if self.reminder is None else "Edit Reminder"
        title_label = tk.Label(main_frame, text=title_text, font=('Segoe UI', 16, 'bold'), 
                              bg='#f8f9fa', fg='#2c3e50')
        title_label.pack(pady=(0, 20))
        
        # Medicine Name
        self.create_input_field(main_frame, "Medicine Name", "e.g., Aspirin", 'name_var')
        
        # Dosage
        self.create_input_field(main_frame, "Dosage", "e.g., 2 tablets, 5ml", 'dosage_var')
        
        # Time
        time_frame = tk.Frame(main_frame, bg='#f8f9fa')
        time_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(time_frame, text="Time", font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#34495e').pack(anchor='w')
        
        time_input_frame = tk.Frame(time_frame, bg='#f8f9fa')
        time_input_frame.pack(fill='x', pady=(5, 0))
        
        self.hour_var = tk.StringVar()
        self.minute_var = tk.StringVar()
        
        hour_frame = tk.Frame(time_input_frame, bg='#f8f9fa')
        hour_frame.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        tk.Label(hour_frame, text="Hour (24h)", font=('Segoe UI', 8), 
                bg='#f8f9fa', fg='#7f8c8d').pack(anchor='w')
        hour_spinbox = tk.Spinbox(hour_frame, from_=0, to=23, textvariable=self.hour_var,
                                 font=('Segoe UI', 11), width=8, justify='center')
        hour_spinbox.pack(fill='x')
        
        minute_frame = tk.Frame(time_input_frame, bg='#f8f9fa')
        minute_frame.pack(side='left', fill='x', expand=True)
        
        tk.Label(minute_frame, text="Minute", font=('Segoe UI', 8), 
                bg='#f8f9fa', fg='#7f8c8d').pack(anchor='w')
        minute_spinbox = tk.Spinbox(minute_frame, from_=0, to=59, textvariable=self.minute_var,
                                   font=('Segoe UI', 11), width=8, justify='center')
        minute_spinbox.pack(fill='x')
        
        # Repeat Options
        repeat_frame = tk.Frame(main_frame, bg='#f8f9fa')
        repeat_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(repeat_frame, text="Repeat", font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#34495e').pack(anchor='w')
        
        self.repeat_var = tk.StringVar(value='Once')
        repeat_options = ['Once', 'Daily', 'Weekly', 'Custom']
        
        repeat_combo = ttk.Combobox(repeat_frame, textvariable=self.repeat_var, 
                                   values=repeat_options, state='readonly', 
                                   font=('Segoe UI', 11), width=30)
        repeat_combo.pack(fill='x', pady=(5, 0))
        repeat_combo.bind("<<ComboboxSelected>>", self.on_repeat_change)
        
        # Custom interval (initially hidden)
        self.custom_frame = tk.Frame(main_frame, bg='#f8f9fa')
        self.create_input_field(self.custom_frame, "Custom Interval (days)", "e.g., 3", 'custom_interval_var')
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='#f8f9fa')
        button_frame.pack(fill='x', pady=(20, 0))
        
        cancel_btn = tk.Button(button_frame, text="Cancel", font=('Segoe UI', 10),
                              bg='#95a5a6', fg='white', relief='flat', padx=20, pady=8,
                              command=self.cancel)
        cancel_btn.pack(side='right', padx=(10, 0))
        
        save_text = "Add Reminder" if self.reminder is None else "Update Reminder"
        save_btn = tk.Button(button_frame, text=save_text, font=('Segoe UI', 10, 'bold'),
                            bg='#3498db', fg='white', relief='flat', padx=20, pady=8,
                            command=self.save)
        save_btn.pack(side='right')
    
    def create_input_field(self, parent, label_text, placeholder, var_name):
        field_frame = tk.Frame(parent, bg='#f8f9fa')
        field_frame.pack(fill='x', pady=(0, 15))
        
        label = tk.Label(field_frame, text=label_text, font=('Segoe UI', 10, 'bold'), 
                        bg='#f8f9fa', fg='#34495e')
        label.pack(anchor='w')
        
        var = tk.StringVar()
        setattr(self, var_name, var)
        
        entry = tk.Entry(field_frame, textvariable=var, font=('Segoe UI', 11), 
                        relief='solid', borderwidth=1, highlightthickness=1)
        entry.pack(fill='x', pady=(5, 0), ipady=5)
        
        entry.insert(0, placeholder)
        entry.config(fg='#bdc3c7')
        
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg='#2c3e50')
        
        def on_focus_out(event):
            if entry.get() == '':
                entry.insert(0, placeholder)
                entry.config(fg='#bdc3c7')
        
        entry.bind('<FocusIn>', on_focus_in)
        entry.bind('<FocusOut>', on_focus_out)
    
    def on_repeat_change(self, event):
        if self.repeat_var.get() == 'Custom':
            self.custom_frame.pack(fill='x', pady=(0, 15))
        else:
            self.custom_frame.pack_forget()
    
    def populate_fields(self):
        if self.reminder:
            self.name_var.set(self.reminder['name'])
            self.dosage_var.set(self.reminder['dosage'])
            
            time_str = self.reminder['time'][-5:]
            hour, minute = time_str.split(':')
            self.hour_var.set(hour)
            self.minute_var.set(minute)
            
            self.repeat_var.set(self.reminder['repeat'])
            if self.reminder['repeat'] == 'Custom':
                self.custom_interval_var.set(str(self.reminder['interval']))
                self.on_repeat_change(None)
    
    def validate_input(self):
        name = self.name_var.get().strip()
        dosage = self.dosage_var.get().strip()
        
        if not name or name in ['e.g., Aspirin']:
            messagebox.showerror("Error", "Please enter a medicine name.")
            return False
        
        if not dosage or dosage in ['e.g., 2 tablets, 5ml']:
            messagebox.showerror("Error", "Please enter the dosage.")
            return False
        
        try:
            hour = int(self.hour_var.get())
            minute = int(self.minute_var.get())
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Please enter valid time.")
            return False
        
        if self.repeat_var.get() == 'Custom':
            try:
                interval = int(self.custom_interval_var.get())
                if interval < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid custom interval (positive number).")
                return False
        
        return True
    
    def save(self):
        if not self.validate_input():
            return
        
        name = self.name_var.get().strip()
        dosage = self.dosage_var.get().strip()
        
        if name == 'e.g., Aspirin':
            name = ''
        if dosage == 'e.g., 2 tablets, 5ml':
            dosage = ''
        
        hour = int(self.hour_var.get())
        minute = int(self.minute_var.get())
        repeat = self.repeat_var.get()
        interval = 0
        
        if repeat == 'Custom':
            interval = int(self.custom_interval_var.get())
        
        now = datetime.now()
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled_time < now:
            scheduled_time += timedelta(days=1)
        
        self.result = {
            'name': name,
            'dosage': dosage,
            'time': scheduled_time.strftime('%Y-%m-%d %H:%M'),
            'repeat': repeat,
            'interval': interval,
            'notified': False,
            'taken': False,
            'enabled': True
        }
        
        self.dialog.destroy()
    
    def cancel(self):
        self.dialog.destroy()

# ─────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────
class MedicineReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("💊 Medicine Reminder")
        self.root.geometry("900x700")
        self.root.configure(bg='#f8f9fa')
        
        # Center window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.root.winfo_screenheight() // 2) - (700 // 2)
        self.root.geometry(f"900x700+{x}+{y}")
        
        self.theme = 'light'
        self.snooze_minutes = 10
        self.db = ReminderDatabase()
        self.reminders = self.db.get_reminders()
        
        self.create_widgets()
        self.update_reminders_display()
        
        self.running = True
        self.check_reminders_thread = threading.Thread(target=self.check_reminders, daemon=True)
        self.check_reminders_thread.start()
        
        if TRAY_ENABLED:
            self.setup_tray_icon()
    
    def create_widgets(self):
        # ── Header ────────────────────────────────────────────────────────
        header_frame = tk.Frame(self.root, bg='#3498db', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        header_content = tk.Frame(header_frame, bg='#3498db')
        header_content.pack(expand=True, fill='both', padx=30, pady=20)
        
        title_label = tk.Label(header_content, text="💊 Medicine Reminder", 
                              font=('Segoe UI', 24, 'bold'), bg='#3498db', fg='white')
        title_label.pack(side='left', anchor='w')
        
        subtitle_label = tk.Label(header_content, text="Never miss your medication again", 
                                 font=('Segoe UI', 11), bg='#3498db', fg='#ecf0f1')
        subtitle_label.pack(side='left', anchor='w', padx=(15, 0))
        
        # Header buttons
        button_frame = tk.Frame(header_content, bg='#3498db')
        button_frame.pack(side='right')

        # ⚙️ Settings button
        settings_btn = tk.Button(button_frame, text="⚙️ Settings", font=('Segoe UI', 10),
                                 bg='#1a5276', fg='white', relief='flat', padx=15, pady=5,
                                 cursor='hand2',
                                 command=self.open_settings)
        settings_btn.pack(side='right', padx=(5, 0))
        self._add_btn_hover(settings_btn, '#154360', '#1a5276')

        refresh_btn = tk.Button(button_frame, text="🔄 Refresh", font=('Segoe UI', 10),
                               bg='#2980b9', fg='white', relief='flat', padx=15, pady=5,
                               command=self.reload_reminders)
        refresh_btn.pack(side='right', padx=(5, 0))
        
        theme_btn = tk.Button(button_frame, text="🌗 Theme", font=('Segoe UI', 10),
                             bg='#2980b9', fg='white', relief='flat', padx=15, pady=5,
                             command=self.toggle_theme)
        theme_btn.pack(side='right', padx=(5, 0))
        
        # ── Main content area ─────────────────────────────────────────────
        content_frame = tk.Frame(self.root, bg='#f8f9fa')
        content_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        # Left panel
        left_panel = tk.Frame(content_frame, bg='white', relief='solid', borderwidth=1)
        left_panel.pack(side='left', fill='y', padx=(0, 15))
        
        quick_add_frame = tk.Frame(left_panel, bg='white', padx=20, pady=20)
        quick_add_frame.pack(fill='x')
        
        tk.Label(quick_add_frame, text="Quick Add Reminder", font=('Segoe UI', 14, 'bold'),
                bg='white', fg='#2c3e50').pack(anchor='w', pady=(0, 15))
        
        add_btn = tk.Button(quick_add_frame, text="+ Add New Reminder", 
                           font=('Segoe UI', 12, 'bold'), bg='#27ae60', fg='white',
                           relief='flat', padx=20, pady=10, command=self.add_reminder)
        add_btn.pack(fill='x')
        
        stats_frame = tk.Frame(left_panel, bg='white', padx=20, pady=20)
        stats_frame.pack(fill='x')
        
        tk.Label(stats_frame, text="Today's Overview", font=('Segoe UI', 12, 'bold'),
                bg='white', fg='#2c3e50').pack(anchor='w', pady=(0, 10))
        
        self.stats_label = tk.Label(stats_frame, text="", font=('Segoe UI', 10),
                                   bg='white', fg='#7f8c8d', justify='left')
        self.stats_label.pack(anchor='w')

        # Settings status indicator
        status_frame = tk.Frame(left_panel, bg='white', padx=20, pady=10)
        status_frame.pack(fill='x')
        tk.Label(status_frame, text="Notification Status", font=('Segoe UI', 10, 'bold'),
                bg='white', fg='#2c3e50').pack(anchor='w', pady=(0, 6))
        self.notif_status_label = tk.Label(status_frame, text="", font=('Segoe UI', 9),
                                           bg='white', fg='#7f8c8d', justify='left')
        self.notif_status_label.pack(anchor='w')
        self._update_notif_status()
        
        # Right panel
        right_panel = tk.Frame(content_frame, bg='white', relief='solid', borderwidth=1)
        right_panel.pack(side='right', fill='both', expand=True)
        
        list_header = tk.Frame(right_panel, bg='#ecf0f1', height=50)
        list_header.pack(fill='x')
        list_header.pack_propagate(False)
        
        tk.Label(list_header, text="Your Reminders", font=('Segoe UI', 14, 'bold'),
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=20, pady=15)
        
        self.reminders_container = tk.Frame(right_panel, bg='white')
        self.reminders_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        self.canvas = tk.Canvas(self.reminders_container, bg='white', highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.reminders_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg='white')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

    # ── Settings helpers ──────────────────────────────────────────────
    def open_settings(self):
        SettingsDialog(self)
        # After dialog closes, refresh the status indicator
        self._update_notif_status()

    def _update_notif_status(self):
        email_ok  = bool(APP_SETTINGS.get('email_address') and APP_SETTINGS.get('email_password'))
        twilio_ok = bool(APP_SETTINGS.get('twilio_account_sid') and APP_SETTINGS.get('twilio_auth_token'))
        lines = [
            f"{'✅' if email_ok  else '❌'} Email {'configured' if email_ok  else 'not set'}",
            f"{'✅' if twilio_ok else '❌'} Twilio {'configured' if twilio_ok else 'not set'}",
        ]
        self.notif_status_label.config(text='\n'.join(lines),
                                       fg='#2c3e50' if (email_ok and twilio_ok) else '#e74c3c')

    def _add_btn_hover(self, btn, hover_color, normal_color):
        btn.bind('<Enter>', lambda e: btn.config(bg=hover_color))
        btn.bind('<Leave>', lambda e: btn.config(bg=normal_color))

    # ── Core app methods (unchanged) ──────────────────────────────────
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def add_reminder(self):
        dialog = ModernReminderDialog(self)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            for rem in self.reminders:
                if (rem['name'].lower() == dialog.result['name'].lower() and 
                    rem['time'][-5:] == dialog.result['time'][-5:]):
                    messagebox.showerror("Duplicate", "A reminder with the same name and time already exists.")
                    return
            
            self.db.add_reminder(dialog.result)
            self.reminders = self.db.get_reminders()
            self.update_reminders_display()
            messagebox.showinfo("Success", "Reminder added successfully!")
    
    def edit_reminder(self, reminder_id):
        reminder = self.db.get_reminder_by_id(reminder_id)
        if not reminder:
            return
        
        dialog = ModernReminderDialog(self, reminder)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            self.db.update_reminder(reminder_id, dialog.result)
            self.reminders = self.db.get_reminders()
            self.update_reminders_display()
            messagebox.showinfo("Success", "Reminder updated successfully!")
    
    def delete_reminder(self, reminder_id):
        result = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this reminder?")
        if result:
            self.db.delete_reminder(reminder_id)
            self.reminders = self.db.get_reminders()
            self.update_reminders_display()
    
    def toggle_reminder(self, reminder_id):
        reminder = self.db.get_reminder_by_id(reminder_id)
        if reminder:
            reminder['enabled'] = not reminder['enabled']
            self.db.update_reminder(reminder_id, reminder)
            self.reminders = self.db.get_reminders()
            self.update_reminders_display()
    
    def mark_as_taken(self, reminder_id):
        reminder = self.db.get_reminder_by_id(reminder_id)
        if reminder:
            reminder['taken'] = True
            self.db.update_reminder(reminder_id, reminder)
            self.reminders = self.db.get_reminders()
            self.update_reminders_display()
    
    def snooze_reminder(self, reminder_id):
        reminder = self.db.get_reminder_by_id(reminder_id)
        if reminder:
            snooze_minutes = simpledialog.askinteger("Snooze", "Snooze for how many minutes?", 
                                                    initialvalue=10, minvalue=1, maxvalue=1440)
            if snooze_minutes:
                t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
                t += timedelta(minutes=snooze_minutes)
                reminder['time'] = t.strftime('%Y-%m-%d %H:%M')
                reminder['notified'] = False
                self.db.update_reminder(reminder_id, reminder)
                self.reminders = self.db.get_reminders()
                self.update_reminders_display()
                messagebox.showinfo("Snoozed", f"Reminder snoozed for {snooze_minutes} minutes.")
    
    def update_reminders_display(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.reminders:
            empty_frame = tk.Frame(self.scrollable_frame, bg='white')
            empty_frame.pack(fill='x', pady=50)
            
            tk.Label(empty_frame, text="📋", font=('Segoe UI', 48), bg='white', fg='#bdc3c7').pack()
            tk.Label(empty_frame, text="No reminders yet", font=('Segoe UI', 16, 'bold'), 
                    bg='white', fg='#7f8c8d').pack(pady=(10, 5))
            tk.Label(empty_frame, text="Click 'Add New Reminder' to get started", 
                    font=('Segoe UI', 12), bg='white', fg='#95a5a6').pack()
        else:
            sorted_reminders = sorted(self.reminders, key=lambda x: x['time'])
            now = datetime.now()
            
            for i, reminder in enumerate(sorted_reminders):
                self.create_reminder_card(reminder, i, now)
        
        self.update_stats()
    
    def create_reminder_card(self, reminder, index, now):
        rem_time = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
        is_today = rem_time.date() == now.date()
        is_overdue = rem_time < now and not reminder['taken']
        is_upcoming = rem_time > now
        
        if reminder['taken']:
            bg_color = '#d5f4e6'
            border_color = '#27ae60'
            status_text = "✅ Taken"
            status_color = '#27ae60'
        elif is_overdue:
            bg_color = '#ffeaa7'
            border_color = '#fdcb6e'
            status_text = "⚠️ Overdue"
            status_color = '#e17055'
        elif is_today and rem_time.hour <= now.hour + 1:
            bg_color = '#74b9ff'
            border_color = '#0984e3'
            status_text = "🔔 Soon"
            status_color = '#0984e3'
        else:
            bg_color = '#f8f9fa'
            border_color = '#e9ecef'
            status_text = "📅 Scheduled"
            status_color = '#6c757d'
        
        card_frame = tk.Frame(self.scrollable_frame, bg=bg_color, relief='solid', 
                             borderwidth=2, bd=2)
        card_frame.configure(highlightbackground=border_color, highlightcolor=border_color)
        card_frame.pack(fill='x', pady=5, padx=5)
        
        content_frame = tk.Frame(card_frame, bg=bg_color, padx=15, pady=12)
        content_frame.pack(fill='x')
        
        top_row = tk.Frame(content_frame, bg=bg_color)
        top_row.pack(fill='x', pady=(0, 8))
        
        medicine_name = tk.Label(top_row, text=reminder['name'], 
                                font=('Segoe UI', 14, 'bold'), bg=bg_color, fg='#2c3e50')
        medicine_name.pack(side='left', anchor='w')
        
        status_label = tk.Label(top_row, text=status_text, font=('Segoe UI', 10, 'bold'),
                               bg=bg_color, fg=status_color)
        status_label.pack(side='right', anchor='e')
        
        middle_row = tk.Frame(content_frame, bg=bg_color)
        middle_row.pack(fill='x', pady=(0, 8))
        
        dosage_info = tk.Label(middle_row, text=f"💊 {reminder['dosage']}", 
                              font=('Segoe UI', 11), bg=bg_color, fg='#34495e')
        dosage_info.pack(side='left', anchor='w')
        
        time_str = rem_time.strftime('%I:%M %p')
        if is_today:
            time_text = f"Today at {time_str}"
        elif rem_time.date() == (now + timedelta(days=1)).date():
            time_text = f"Tomorrow at {time_str}"
        else:
            time_text = rem_time.strftime('%b %d at %I:%M %p')
        
        time_info = tk.Label(middle_row, text=f"🕐 {time_text}", 
                            font=('Segoe UI', 11), bg=bg_color, fg='#34495e')
        time_info.pack(side='right', anchor='e')
        
        if reminder['repeat'] != 'Once':
            repeat_info = tk.Label(content_frame, text=f"🔄 Repeats {reminder['repeat'].lower()}", 
                                  font=('Segoe UI', 9), bg=bg_color, fg='#7f8c8d')
            repeat_info.pack(anchor='w', pady=(0, 8))
        
        button_frame = tk.Frame(content_frame, bg=bg_color)
        button_frame.pack(fill='x')
        
        toggle_text = "Disable" if reminder.get('enabled', True) else "Enable"
        toggle_color = '#e74c3c' if reminder.get('enabled', True) else '#27ae60'
        
        toggle_btn = tk.Button(button_frame, text=toggle_text, font=('Segoe UI', 9),
                              bg=toggle_color, fg='white', relief='flat', padx=12, pady=4,
                              command=lambda: self.toggle_reminder(reminder['id']))
        toggle_btn.pack(side='left', padx=(0, 5))
        
        if not reminder['taken'] and reminder.get('enabled', True):
            take_btn = tk.Button(button_frame, text="✅ Take", font=('Segoe UI', 9),
                                bg='#27ae60', fg='white', relief='flat', padx=12, pady=4,
                                command=lambda: self.mark_as_taken(reminder['id']))
            take_btn.pack(side='left', padx=(0, 5))
            
            snooze_btn = tk.Button(button_frame, text="😴 Snooze", font=('Segoe UI', 9),
                                  bg='#f39c12', fg='white', relief='flat', padx=12, pady=4,
                                  command=lambda: self.snooze_reminder(reminder['id']))
            snooze_btn.pack(side='left', padx=(0, 5))
        
        edit_btn = tk.Button(button_frame, text="✏️ Edit", font=('Segoe UI', 9),
                            bg='#3498db', fg='white', relief='flat', padx=12, pady=4,
                            command=lambda: self.edit_reminder(reminder['id']))
        edit_btn.pack(side='right', padx=(5, 0))
        
        delete_btn = tk.Button(button_frame, text="🗑️ Delete", font=('Segoe UI', 9),
                              bg='#e74c3c', fg='white', relief='flat', padx=12, pady=4,
                              command=lambda: self.delete_reminder(reminder['id']))
        delete_btn.pack(side='right', padx=(5, 0))
        
        self.add_hover_effect(card_frame, bg_color, border_color)
    
    def add_hover_effect(self, widget, normal_bg, normal_border):
        def on_enter(event):
            widget.configure(bg=self.darken_color(normal_bg))
        
        def on_leave(event):
            widget.configure(bg=normal_bg)
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def darken_color(self, hex_color):
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened_rgb = tuple(max(0, c - 20) for c in rgb)
        return f"#{darkened_rgb[0]:02x}{darkened_rgb[1]:02x}{darkened_rgb[2]:02x}"
    
    def update_stats(self):
        now = datetime.now()
        today = now.date()
        
        total_reminders = len(self.reminders)
        today_reminders = len([r for r in self.reminders if datetime.strptime(r['time'], "%Y-%m-%d %H:%M").date() == today])
        taken_today = len([r for r in self.reminders if r['taken'] and datetime.strptime(r['time'], "%Y-%m-%d %H:%M").date() == today])
        overdue = len([r for r in self.reminders if datetime.strptime(r['time'], "%Y-%m-%d %H:%M") < now and not r['taken']])
        
        stats_text = f"""📊 Total Reminders: {total_reminders}
📅 Today's Reminders: {today_reminders}
✅ Taken Today: {taken_today}
⚠️ Overdue: {overdue}"""
        
        self.stats_label.config(text=stats_text)
    
    def reload_reminders(self):
        self.reminders = self.db.get_reminders()
        self.update_reminders_display()
    
    def toggle_theme(self):
        if self.theme == 'light':
            self.theme = 'dark'
            self.root.configure(bg='#2c3e50')
        else:
            self.theme = 'light'
            self.root.configure(bg='#f8f9fa')
    
    def check_reminders(self):
        while self.running:
            now = datetime.now().replace(second=0, microsecond=0)
            for rem in self.db.get_reminders():
                if not rem.get('enabled', True):
                    continue
                    
                rem_time = datetime.strptime(rem['time'], "%Y-%m-%d %H:%M")
                if rem_time <= now and not rem.get('notified', False) and not rem.get('taken', False):
                    self.show_reminder(rem)
                    updated_rem = rem.copy()
                    updated_rem['notified'] = True
                    self.db.update_reminder(rem['id'], updated_rem)
            time.sleep(30)
    
    def show_reminder(self, reminder):
        def popup():
            msg = f"Time to take your medicine:\n\nName: {reminder['name']}\nDosage: {reminder['dosage']}\nTime: {reminder['time'][-5:]}"
            play_sound()
            show_tray_notification("Medicine Reminder", msg)
            send_email("Medicine Reminder", msg)
            make_call(f"Reminder! It's time to take your medicine {reminder['name']}, dosage {reminder['dosage']}.")
            
            popup_window = tk.Toplevel(self.root)
            popup_window.title("Medicine Reminder")
            popup_window.geometry("400x300")
            popup_window.configure(bg='#fff3cd')
            popup_window.transient(self.root)
            popup_window.grab_set()
            
            popup_window.update_idletasks()
            x = (popup_window.winfo_screenwidth() // 2) - (400 // 2)
            y = (popup_window.winfo_screenheight() // 2) - (300 // 2)
            popup_window.geometry(f"400x300+{x}+{y}")
            
            content_frame = tk.Frame(popup_window, bg='#fff3cd', padx=30, pady=30)
            content_frame.pack(fill='both', expand=True)
            
            tk.Label(content_frame, text="💊", font=('Segoe UI', 48), bg='#fff3cd').pack(pady=(0, 10))
            tk.Label(content_frame, text="Time for your medicine!", font=('Segoe UI', 16, 'bold'),
                    bg='#fff3cd', fg='#856404').pack(pady=(0, 20))
            
            details_frame = tk.Frame(content_frame, bg='#fff3cd')
            details_frame.pack(pady=(0, 20))
            
            tk.Label(details_frame, text=f"Medicine: {reminder['name']}", font=('Segoe UI', 12, 'bold'),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            tk.Label(details_frame, text=f"Dosage: {reminder['dosage']}", font=('Segoe UI', 12),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            tk.Label(details_frame, text=f"Time: {reminder['time'][-5:]}", font=('Segoe UI', 12),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            
            button_frame = tk.Frame(content_frame, bg='#fff3cd')
            button_frame.pack(fill='x')
            
            def mark_taken():
                updated_rem = reminder.copy()
                updated_rem['taken'] = True
                self.handle_recurring_reminder(updated_rem)
                popup_window.destroy()
                self.update_reminders_display()
            
            def snooze():
                snooze_minutes = simpledialog.askinteger("Snooze", "Snooze for how many minutes?", 
                                                        initialvalue=10, minvalue=1, maxvalue=1440)
                if snooze_minutes:
                    t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
                    updated_rem = reminder.copy()
                    updated_rem['time'] = (t + timedelta(minutes=snooze_minutes)).strftime('%Y-%m-%d %H:%M')
                    updated_rem['notified'] = False
                    self.db.update_reminder(reminder['id'], updated_rem)
                    popup_window.destroy()
                    self.update_reminders_display()
            
            taken_btn = tk.Button(button_frame, text="✅ Mark as Taken", font=('Segoe UI', 11, 'bold'),
                                 bg='#28a745', fg='white', relief='flat', padx=20, pady=8,
                                 command=mark_taken)
            taken_btn.pack(side='left', padx=(0, 10))
            
            snooze_btn = tk.Button(button_frame, text="😴 Snooze", font=('Segoe UI', 11),
                                  bg='#ffc107', fg='#212529', relief='flat', padx=20, pady=8,
                                  command=snooze)
            snooze_btn.pack(side='left')
            
            dismiss_btn = tk.Button(button_frame, text="❌ Dismiss", font=('Segoe UI', 11),
                                   bg='#6c757d', fg='white', relief='flat', padx=20, pady=8,
                                   command=popup_window.destroy)
            dismiss_btn.pack(side='right')
            
        self.root.after(0, popup)
    
    def handle_recurring_reminder(self, reminder):
        """Handle recurring reminders when marked as taken"""
        updated_rem = reminder.copy()
        
        if reminder['repeat'] == 'Daily':
            t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M") + timedelta(days=1)
            updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
            updated_rem['notified'] = False
            updated_rem['taken'] = False
        elif reminder['repeat'] == 'Weekly':
            t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M") + timedelta(days=7)
            updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
            updated_rem['notified'] = False
            updated_rem['taken'] = False
        elif reminder['repeat'] == 'Custom':
            interval = reminder.get('interval', 1)
            t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M") + timedelta(days=interval)
            updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
            updated_rem['notified'] = False
            updated_rem['taken'] = False
        
        self.db.update_reminder(reminder['id'], updated_rem)
    
    def setup_tray_icon(self):
        def create_image():
            image = Image.new('RGB', (64, 64), color=(52, 152, 219))
            d = ImageDraw.Draw(image)
            d.ellipse((16, 16, 48, 48), fill=(255, 255, 255))
            d.text((32, 32), "💊", anchor="mm")
            return image
        
        image = create_image()
        icon = pystray.Icon("medicine_reminder", image, "Medicine Reminder")
        
        def on_activate(icon, item):
            self.root.deiconify()
            self.root.lift()
        
        icon.menu = pystray.Menu(pystray.MenuItem("Show", on_activate))
        
        def on_closing():
            self.root.withdraw()
            icon.run_detached()
        
        self.root.protocol("WM_DELETE_WINDOW", on_closing)
    
    def on_closing(self):
        self.running = False
        self.db.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = MedicineReminderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()