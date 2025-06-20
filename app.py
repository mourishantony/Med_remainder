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
import sqlite3
from email.mime.text import MIMEText

EMAIL_ENABLED = True
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "email_address": os.getenv("EMAIL_ADDRESS"),
    "email_password": os.getenv("EMAIL_PASSWORD"),
    "recipient_email": os.getenv("RECIPIENT_EMAIL")
}

TWILIO_ENABLED = True
TWILIO_CONFIG = {
    "account_sid": os.getenv("TWILIO_ACCOUNT_SID"),
    "auth_token": os.getenv("TWILIO_AUTH_TOKEN"),
    "from_number": os.getenv("TWILIO_FROM_NUMBER"),
    "to_number": os.getenv("TWILIO_TO_NUMBER")
}

try:
    from twilio.rest import Client
except ImportError:
    TWILIO_ENABLED = False

def make_call(message):
    if not TWILIO_ENABLED:
        return
    try:
        client = Client(TWILIO_CONFIG["account_sid"], TWILIO_CONFIG["auth_token"])
        call = client.calls.create(
            to=TWILIO_CONFIG["to_number"],
            from_=TWILIO_CONFIG["from_number"],
            twiml=f'<Response><Say>{message}</Say></Response>'
        )
        print("Twilio call initiated. SID:", call.sid)
    except Exception as e:
        print("Failed to make Twilio call:", e)

# For sound notifications
try:
    import pygame
    SOUND_ENABLED = True
except ImportError:
    SOUND_ENABLED = False

# For system tray notifications (Windows)
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_ENABLED = True
except ImportError:
    TRAY_ENABLED = False

DB_FILE = 'reminders.db'

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
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG["email_address"]
        msg['To'] = EMAIL_CONFIG["recipient_email"]
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(EMAIL_CONFIG["email_address"], EMAIL_CONFIG["email_password"])
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
    else:
        pass  # fallback: do nothing

class ReminderDatabase:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.create_table()

    def create_table(self):
        cur = self.conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            time TEXT NOT NULL,
            repeat TEXT NOT NULL,
            interval INTEGER NOT NULL,
            notified INTEGER NOT NULL,
            taken INTEGER NOT NULL
        )
        ''')
        self.conn.commit()

    def add_reminder(self, reminder):
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO reminders (name, dosage, time, repeat, interval, notified, taken)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (reminder['name'], reminder['dosage'], reminder['time'],
              reminder['repeat'], reminder['interval'],
              int(reminder['notified']), int(reminder['taken'])))
        self.conn.commit()

    def update_reminder(self, idx, reminder):
        cur = self.conn.cursor()
        cur.execute('''
            UPDATE reminders SET
                name = ?,
                dosage = ?,
                time = ?,
                repeat = ?,
                interval = ?,
                notified = ?,
                taken = ?
            WHERE id = ?
        ''', (reminder['name'], reminder['dosage'], reminder['time'],
              reminder['repeat'], reminder['interval'],
              int(reminder['notified']), int(reminder['taken']), idx))
        self.conn.commit()

    def delete_reminder(self, idx):
        cur = self.conn.cursor()
        cur.execute('DELETE FROM reminders WHERE id = ?', (idx,))
        self.conn.commit()

    def get_reminders(self):
        cur = self.conn.cursor()
        cur.execute('SELECT id, name, dosage, time, repeat, interval, notified, taken FROM reminders')
        result = []
        for row in cur.fetchall():
            result.append({
                'id': row[0],
                'name': row[1],
                'dosage': row[2],
                'time': row[3],
                'repeat': row[4],
                'interval': row[5],
                'notified': bool(row[6]),
                'taken': bool(row[7])
            })
        return result

    def get_reminder_by_id(self, idx):
        cur = self.conn.cursor()
        cur.execute('SELECT id, name, dosage, time, repeat, interval, notified, taken FROM reminders WHERE id = ?', (idx,))
        row = cur.fetchone()
        if row:
            return {
                'id': row[0],
                'name': row[1],
                'dosage': row[2],
                'time': row[3],
                'repeat': row[4],
                'interval': row[5],
                'notified': bool(row[6]),
                'taken': bool(row[7])
            }
        return None

    def close(self):
        self.conn.close()

class MedicineReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("💊 Medicine Reminder")
        self.root.geometry("640x520")
        self.root.resizable(False, False)
        self.theme = 'light'
        self.snooze_minutes = 10
        self.db = ReminderDatabase()
        self.reminders = self.db.get_reminders()

        self.setup_styles()
        self.create_widgets()
        self.update_reminders_list()

        self.running = True
        self.check_reminders_thread = threading.Thread(target=self.check_reminders, daemon=True)
        self.check_reminders_thread.start()

        if TRAY_ENABLED:
            self.setup_tray_icon()

    def setup_styles(self):
        self.style = ttk.Style()
        self.set_theme(self.theme)

    def set_theme(self, theme):
        if theme == 'dark':
            bg = '#222'
            fg = '#eee'
            self.style.theme_use("clam")
            self.style.configure('.', background=bg, foreground=fg, fieldbackground=bg)
            self.root.configure(bg=bg)
        else:
            bg = '#f2f2f2'
            fg = '#222'
            self.style.theme_use("clam")
            self.style.configure('.', background=bg, foreground=fg, fieldbackground=bg)
            self.root.configure(bg=bg)

    def create_widgets(self):
        # Header
        frame_header = ttk.Frame(self.root, padding=10)
        frame_header.pack(fill='x')
        ttk.Label(frame_header, text="Medicine Reminder", font=('Segoe UI', 18, 'bold')).pack(side='left')
        ttk.Button(frame_header, text="🌗 Theme", command=self.toggle_theme).pack(side='right', padx=2)
        ttk.Button(frame_header, text="🔄 Reload", command=self.reload_reminders).pack(side='right', padx=2)

        # Input
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill='x')
        ttk.Label(frame, text="Medicine Name:").grid(row=0, column=0, sticky='w', pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=25)
        self.name_entry.grid(row=0, column=1, sticky='ew', pady=4)

        ttk.Label(frame, text="Dosage:").grid(row=1, column=0, sticky='w', pady=4)
        self.dosage_var = tk.StringVar()
        self.dosage_entry = ttk.Entry(frame, textvariable=self.dosage_var, width=25)
        self.dosage_entry.grid(row=1, column=1, sticky='ew', pady=4)

        ttk.Label(frame, text="Time (HH:MM, 24hr):").grid(row=2, column=0, sticky='w', pady=4)
        self.time_var = tk.StringVar()
        self.time_entry = ttk.Entry(frame, textvariable=self.time_var, width=25)
        self.time_entry.grid(row=2, column=1, sticky='ew', pady=4)

        ttk.Label(frame, text="Repeat:").grid(row=3, column=0, sticky='w', pady=4)
        self.repeat_var = tk.StringVar(value='Once')
        repeat_options = ['Once', 'Daily', 'Weekly', 'Custom']
        self.repeat_combo = ttk.Combobox(frame, textvariable=self.repeat_var, values=repeat_options, state='readonly', width=22)
        self.repeat_combo.grid(row=3, column=1, sticky='ew', pady=4)
        self.repeat_combo.bind("<<ComboboxSelected>>", self.on_repeat_change)

        self.custom_interval_label = ttk.Label(frame, text="Custom interval (days):")
        self.custom_interval_var = tk.StringVar()
        self.custom_interval_entry = ttk.Entry(frame, textvariable=self.custom_interval_var, width=10)

        add_btn = ttk.Button(self.root, text="Add Reminder", command=self.add_reminder)
        add_btn.pack(pady=8)

        # Reminders List
        ttk.Label(self.root, text="Scheduled Reminders:", font=('Segoe UI', 12, 'bold')).pack()
        list_frame = ttk.Frame(self.root, padding=5)
        list_frame.pack(fill='both', expand=True)
        self.reminders_list = tk.Listbox(list_frame, height=12, font=('Segoe UI', 10), selectmode='browse')
        self.reminders_list.pack(side='left', fill='both', expand=True)
        self.reminders_list.bind('<Double-Button-1>', self.edit_selected_reminder)
        sb = ttk.Scrollbar(list_frame, orient='vertical', command=self.reminders_list.yview)
        self.reminders_list.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')

        # Control Buttons
        controls = ttk.Frame(self.root, padding=10)
        controls.pack()
        ttk.Button(controls, text="Edit", command=self.edit_selected_reminder).pack(side='left', padx=5)
        ttk.Button(controls, text="Delete", command=self.delete_selected_reminder).pack(side='left', padx=5)
        ttk.Button(controls, text="Mark as Taken", command=self.mark_as_taken).pack(side='left', padx=5)
        ttk.Button(controls, text="Snooze", command=self.snooze_reminder).pack(side='left', padx=5)

    def on_repeat_change(self, event):
        if self.repeat_var.get() == 'Custom':
            self.custom_interval_label.grid(row=4, column=0, sticky='w', pady=4)
            self.custom_interval_entry.grid(row=4, column=1, sticky='ew', pady=4)
        else:
            self.custom_interval_label.grid_forget()
            self.custom_interval_entry.grid_forget()

    def validate_time(self, time_str):
        try:
            datetime.strptime(time_str, '%H:%M')
            return True
        except ValueError:
            return False

    def reminder_duplicate(self, name, time_str):
        # Duplicate if same name and time
        for rem in self.reminders:
            if rem['name'].lower() == name.lower() and rem['time'][-5:] == time_str:
                return True
        return False

    def add_reminder(self):
        name = self.name_var.get().strip()
        dosage = self.dosage_var.get().strip()
        time_str = self.time_var.get().strip()
        repeat = self.repeat_var.get()
        interval = 0

        # Input validation
        if not name or not dosage or not time_str:
            messagebox.showerror("Input Error", "Please fill all fields.")
            return
        if not self.validate_time(time_str):
            messagebox.showerror("Input Error", "Invalid time format. Use HH:MM (24-hour).")
            return
        if self.reminder_duplicate(name, time_str):
            messagebox.showerror("Duplicate", "A reminder with the same name and time already exists.")
            return
        if repeat == 'Custom':
            try:
                interval = int(self.custom_interval_var.get().strip())
                if interval < 1:
                    raise ValueError
            except Exception:
                messagebox.showerror("Input Error", "Custom interval must be a positive integer.")
                return

        now = datetime.now()
        t = datetime.strptime(time_str, '%H:%M')
        scheduled_time = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if scheduled_time < now:
            scheduled_time += timedelta(days=1)

        reminder = {
            'name': name,
            'dosage': dosage,
            'time': scheduled_time.strftime('%Y-%m-%d %H:%M'),
            'repeat': repeat,
            'interval': interval,
            'notified': False,
            'taken': False
        }
        self.db.add_reminder(reminder)
        self.reminders = self.db.get_reminders()
        self.update_reminders_list()
        self.clear_inputs()

    def clear_inputs(self):
        self.name_var.set('')
        self.dosage_var.set('')
        self.time_var.set('')
        self.repeat_var.set('Once')
        self.custom_interval_var.set('')
        self.on_repeat_change(None)

    def update_reminders_list(self):
        self.reminders = self.db.get_reminders()
        self.reminders.sort(key=lambda x: x['time'])
        self.reminders_list.delete(0, tk.END)
        now = datetime.now()
        for idx, rem in enumerate(self.reminders):
            tstr = datetime.strptime(rem['time'], "%Y-%m-%d %H:%M").strftime('%Y-%m-%d %H:%M')
            repeat = rem['repeat']
            extra = ''
            if rem['taken']:
                extra += ' [Taken]'
            if datetime.strptime(rem['time'], "%Y-%m-%d %H:%M") < now:
                extra += ' [Missed]'
            self.reminders_list.insert(tk.END, f"{rem['name']} | {rem['dosage']} | {tstr} | {repeat}{extra}")

    def save_reminders(self):
        # No longer needed, database handles saving
        pass

    def load_reminders(self):
        self.reminders = self.db.get_reminders()

    def reload_reminders(self):
        self.load_reminders()
        self.update_reminders_list()

    def get_selected_index(self):
        selected = self.reminders_list.curselection()
        if not selected:
            messagebox.showinfo("Select", "Please select a reminder first.")
            return None
        return selected[0]

    def edit_selected_reminder(self, event=None):
        idx = self.get_selected_index()
        if idx is None:
            return
        rem = self.reminders[idx]
        new_name = simpledialog.askstring("Edit Name", "Edit medicine name:", initialvalue=rem['name'])
        if not new_name:
            return
        new_dosage = simpledialog.askstring("Edit Dosage", "Edit dosage:", initialvalue=rem['dosage'])
        if not new_dosage:
            return
        new_time = simpledialog.askstring("Edit Time", "Edit time (HH:MM):", initialvalue=rem['time'][-5:])
        if not new_time or not self.validate_time(new_time):
            messagebox.showerror("Input Error", "Invalid time format. Use HH:MM (24-hour).")
            return
        now = datetime.now()
        t = datetime.strptime(new_time, '%H:%M')
        scheduled_time = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if scheduled_time < now:
            scheduled_time += timedelta(days=1)
        new_repeat = simpledialog.askstring("Edit Repeat", "Repeat (Once/Daily/Weekly/Custom):", initialvalue=rem['repeat'])
        if not new_repeat or new_repeat not in ['Once', 'Daily', 'Weekly', 'Custom']:
            messagebox.showerror("Input Error", "Repeat must be Once, Daily, Weekly, or Custom.")
            return
        new_interval = 0
        if new_repeat == 'Custom':
            try:
                new_interval = int(simpledialog.askstring("Interval", "Custom interval (days):", initialvalue=str(rem.get('interval', 1))))
            except Exception:
                messagebox.showerror("Input Error", "Invalid interval.")
                return
        updated_rem = {
            'name': new_name,
            'dosage': new_dosage,
            'time': scheduled_time.strftime('%Y-%m-%d %H:%M'),
            'repeat': new_repeat,
            'interval': new_interval,
            'notified': False,
            'taken': False
        }
        self.db.update_reminder(rem['id'], updated_rem)
        self.reminders = self.db.get_reminders()
        self.update_reminders_list()

    def delete_selected_reminder(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        rem = self.reminders[idx]
        res = messagebox.askyesno("Delete?", "Are you sure you want to delete this reminder?")
        if res:
            self.db.delete_reminder(rem['id'])
            self.reminders = self.db.get_reminders()
            self.update_reminders_list()

    def mark_as_taken(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        rem = self.reminders[idx]
        updated_rem = rem.copy()
        updated_rem['taken'] = True
        self.db.update_reminder(rem['id'], updated_rem)
        self.reminders = self.db.get_reminders()
        self.update_reminders_list()

    def snooze_reminder(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        rem = self.reminders[idx]
        snooze_time = simpledialog.askinteger("Snooze", "Snooze for how many minutes?", initialvalue=self.snooze_minutes)
        if snooze_time:
            t = datetime.strptime(rem['time'], "%Y-%m-%d %H:%M")
            t += timedelta(minutes=snooze_time)
            updated_rem = rem.copy()
            updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
            updated_rem['notified'] = False
            self.db.update_reminder(rem['id'], updated_rem)
            self.reminders = self.db.get_reminders()
            self.update_reminders_list()
            messagebox.showinfo("Snoozed", f"Snoozed for {snooze_time} minutes.")

    def check_reminders(self):
        while self.running:
            now = datetime.now().replace(second=0, microsecond=0)
            for rem in self.db.get_reminders():
                rem_time = datetime.strptime(rem['time'], "%Y-%m-%d %H:%M")
                if rem_time <= now and not rem.get('notified', False) and not rem.get('taken', False):
                    self.show_reminder(rem)
                    # update notified status in db
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
            res = messagebox.askyesnocancel("Medicine Reminder", msg + "\n\nTaken? Yes, Snooze, or Cancel.")
            updated_rem = reminder.copy()
            if res is True:
                updated_rem['taken'] = True
            elif res is False:
                snooze = simpledialog.askinteger("Snooze", "Snooze for how many minutes?", initialvalue=10)
                if snooze:
                    t = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
                    updated_rem['time'] = t + timedelta(minutes=snooze)
                    updated_rem['time'] = updated_rem['time'].strftime('%Y-%m-%d %H:%M')
                    updated_rem['notified'] = False
            # Recurring logic
            if reminder['repeat'] == 'Daily' and (updated_rem['taken'] or res is not None):
                t = datetime.strptime(updated_rem['time'], "%Y-%m-%d %H:%M") + timedelta(days=1)
                updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
                updated_rem['notified'] = False
                updated_rem['taken'] = False
            elif reminder['repeat'] == 'Weekly' and (updated_rem['taken'] or res is not None):
                t = datetime.strptime(updated_rem['time'], "%Y-%m-%d %H:%M") + timedelta(days=7)
                updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
                updated_rem['notified'] = False
                updated_rem['taken'] = False
            elif reminder['repeat'] == 'Custom' and (updated_rem['taken'] or res is not None):
                interval = reminder.get('interval', 1)
                t = datetime.strptime(updated_rem['time'], "%Y-%m-%d %H:%M") + timedelta(days=interval)
                updated_rem['time'] = t.strftime('%Y-%m-%d %H:%M')
                updated_rem['notified'] = False
                updated_rem['taken'] = False
            self.db.update_reminder(reminder['id'], updated_rem)
            self.reminders = self.db.get_reminders()
            self.update_reminders_list()
        self.root.after(0, popup)

    def toggle_theme(self):
        self.theme = 'dark' if self.theme == 'light' else 'light'
        self.set_theme(self.theme)

    def setup_tray_icon(self):
        def create_image():
            image = Image.new('RGB', (64, 64), color=(0, 64, 128))
            d = ImageDraw.Draw(image)
            d.ellipse((16, 16, 48, 48), fill=(255, 255, 0))
            return image
        image = create_image()
        icon = pystray.Icon("reminder", image, "Medicine Reminder")
        def on_activate(icon, item):
            self.root.deiconify()
        icon.menu = pystray.Menu(pystray.MenuItem("Restore", on_activate))
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