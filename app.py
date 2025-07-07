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

# Configuration
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

# Sound and tray notifications
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
        
        # Cancel button
        cancel_btn = tk.Button(button_frame, text="Cancel", font=('Segoe UI', 10),
                              bg='#95a5a6', fg='white', relief='flat', padx=20, pady=8,
                              command=self.cancel)
        cancel_btn.pack(side='right', padx=(10, 0))
        
        # Save button
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
        
        # Add placeholder effect
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
            # Remove placeholder text and populate with actual values
            self.name_var.set(self.reminder['name'])
            self.dosage_var.set(self.reminder['dosage'])
            
            # Parse time
            time_str = self.reminder['time'][-5:]  # Get HH:MM
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
        
        # Check if fields are empty or contain placeholder text
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
        
        # Clean up input values
        name = self.name_var.get().strip()
        dosage = self.dosage_var.get().strip()
        
        # Remove placeholder text if present
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
        
        # Create scheduled time
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
        # Header
        header_frame = tk.Frame(self.root, bg='#3498db', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        header_content = tk.Frame(header_frame, bg='#3498db')
        header_content.pack(expand=True, fill='both', padx=30, pady=20)
        
        # Title and subtitle
        title_label = tk.Label(header_content, text="💊 Medicine Reminder", 
                              font=('Segoe UI', 24, 'bold'), bg='#3498db', fg='white')
        title_label.pack(side='left', anchor='w')
        
        subtitle_label = tk.Label(header_content, text="Never miss your medication again", 
                                 font=('Segoe UI', 11), bg='#3498db', fg='#ecf0f1')
        subtitle_label.pack(side='left', anchor='w', padx=(15, 0))
        
        # Header buttons
        button_frame = tk.Frame(header_content, bg='#3498db')
        button_frame.pack(side='right')
        
        refresh_btn = tk.Button(button_frame, text="🔄 Refresh", font=('Segoe UI', 10),
                               bg='#2980b9', fg='white', relief='flat', padx=15, pady=5,
                               command=self.reload_reminders)
        refresh_btn.pack(side='right', padx=(5, 0))
        
        theme_btn = tk.Button(button_frame, text="🌗 Theme", font=('Segoe UI', 10),
                             bg='#2980b9', fg='white', relief='flat', padx=15, pady=5,
                             command=self.toggle_theme)
        theme_btn.pack(side='right', padx=(5, 0))
        
        # Main content area
        content_frame = tk.Frame(self.root, bg='#f8f9fa')
        content_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        # Left panel - Add reminder
        left_panel = tk.Frame(content_frame, bg='white', relief='solid', borderwidth=1)
        left_panel.pack(side='left', fill='y', padx=(0, 15))
        
        # Quick add section
        quick_add_frame = tk.Frame(left_panel, bg='white', padx=20, pady=20)
        quick_add_frame.pack(fill='x')
        
        tk.Label(quick_add_frame, text="Quick Add Reminder", font=('Segoe UI', 14, 'bold'),
                bg='white', fg='#2c3e50').pack(anchor='w', pady=(0, 15))
        
        add_btn = tk.Button(quick_add_frame, text="+ Add New Reminder", 
                           font=('Segoe UI', 12, 'bold'), bg='#27ae60', fg='white',
                           relief='flat', padx=20, pady=10, command=self.add_reminder)
        add_btn.pack(fill='x')
        
        # Stats section
        stats_frame = tk.Frame(left_panel, bg='white', padx=20, pady=20)
        stats_frame.pack(fill='x')
        
        tk.Label(stats_frame, text="Today's Overview", font=('Segoe UI', 12, 'bold'),
                bg='white', fg='#2c3e50').pack(anchor='w', pady=(0, 10))
        
        self.stats_label = tk.Label(stats_frame, text="", font=('Segoe UI', 10),
                                   bg='white', fg='#7f8c8d', justify='left')
        self.stats_label.pack(anchor='w')
        
        # Right panel - Reminders list
        right_panel = tk.Frame(content_frame, bg='white', relief='solid', borderwidth=1)
        right_panel.pack(side='right', fill='both', expand=True)
        
        # List header
        list_header = tk.Frame(right_panel, bg='#ecf0f1', height=50)
        list_header.pack(fill='x')
        list_header.pack_propagate(False)
        
        tk.Label(list_header, text="Your Reminders", font=('Segoe UI', 14, 'bold'),
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=20, pady=15)
        
        # Reminders container
        self.reminders_container = tk.Frame(right_panel, bg='white')
        self.reminders_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Scrollable frame for reminders
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
        
        # Bind mousewheel to canvas
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def add_reminder(self):
        dialog = ModernReminderDialog(self)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            # Check for duplicates
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
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.reminders:
            # Show empty state
            empty_frame = tk.Frame(self.scrollable_frame, bg='white')
            empty_frame.pack(fill='x', pady=50)
            
            tk.Label(empty_frame, text="📋", font=('Segoe UI', 48), bg='white', fg='#bdc3c7').pack()
            tk.Label(empty_frame, text="No reminders yet", font=('Segoe UI', 16, 'bold'), 
                    bg='white', fg='#7f8c8d').pack(pady=(10, 5))
            tk.Label(empty_frame, text="Click 'Add New Reminder' to get started", 
                    font=('Segoe UI', 12), bg='white', fg='#95a5a6').pack()
        else:
            # Sort reminders by time
            sorted_reminders = sorted(self.reminders, key=lambda x: x['time'])
            now = datetime.now()
            
            for i, reminder in enumerate(sorted_reminders):
                self.create_reminder_card(reminder, i, now)
        
        # Update stats
        self.update_stats()
    
    def create_reminder_card(self, reminder, index, now):
        # Determine card status and colors
        rem_time = datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
        is_today = rem_time.date() == now.date()
        is_overdue = rem_time < now and not reminder['taken']
        is_upcoming = rem_time > now
        
        # Color scheme based on status
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
        
        # Main card frame
        card_frame = tk.Frame(self.scrollable_frame, bg=bg_color, relief='solid', 
                             borderwidth=2, bd=2)
        card_frame.configure(highlightbackground=border_color, highlightcolor=border_color)
        card_frame.pack(fill='x', pady=5, padx=5)
        
        # Card content
        content_frame = tk.Frame(card_frame, bg=bg_color, padx=15, pady=12)
        content_frame.pack(fill='x')
        
        # Top row - Medicine name and status
        top_row = tk.Frame(content_frame, bg=bg_color)
        top_row.pack(fill='x', pady=(0, 8))
        
        medicine_name = tk.Label(top_row, text=reminder['name'], 
                                font=('Segoe UI', 14, 'bold'), bg=bg_color, fg='#2c3e50')
        medicine_name.pack(side='left', anchor='w')
        
        status_label = tk.Label(top_row, text=status_text, font=('Segoe UI', 10, 'bold'),
                               bg=bg_color, fg=status_color)
        status_label.pack(side='right', anchor='e')
        
        # Middle row - Dosage and time
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
        
        # Repeat info
        if reminder['repeat'] != 'Once':
            repeat_info = tk.Label(content_frame, text=f"🔄 Repeats {reminder['repeat'].lower()}", 
                                  font=('Segoe UI', 9), bg=bg_color, fg='#7f8c8d')
            repeat_info.pack(anchor='w', pady=(0, 8))
        
        # Action buttons
        button_frame = tk.Frame(content_frame, bg=bg_color)
        button_frame.pack(fill='x')
        
        # Enable/Disable toggle
        toggle_text = "Disable" if reminder.get('enabled', True) else "Enable"
        toggle_color = '#e74c3c' if reminder.get('enabled', True) else '#27ae60'
        
        toggle_btn = tk.Button(button_frame, text=toggle_text, font=('Segoe UI', 9),
                              bg=toggle_color, fg='white', relief='flat', padx=12, pady=4,
                              command=lambda: self.toggle_reminder(reminder['id']))
        toggle_btn.pack(side='left', padx=(0, 5))
        
        if not reminder['taken'] and reminder.get('enabled', True):
            # Take button
            take_btn = tk.Button(button_frame, text="✅ Take", font=('Segoe UI', 9),
                                bg='#27ae60', fg='white', relief='flat', padx=12, pady=4,
                                command=lambda: self.mark_as_taken(reminder['id']))
            take_btn.pack(side='left', padx=(0, 5))
            
            # Snooze button
            snooze_btn = tk.Button(button_frame, text="😴 Snooze", font=('Segoe UI', 9),
                                  bg='#f39c12', fg='white', relief='flat', padx=12, pady=4,
                                  command=lambda: self.snooze_reminder(reminder['id']))
            snooze_btn.pack(side='left', padx=(0, 5))
        
        # Edit and Delete buttons
        edit_btn = tk.Button(button_frame, text="✏️ Edit", font=('Segoe UI', 9),
                            bg='#3498db', fg='white', relief='flat', padx=12, pady=4,
                            command=lambda: self.edit_reminder(reminder['id']))
        edit_btn.pack(side='right', padx=(5, 0))
        
        delete_btn = tk.Button(button_frame, text="🗑️ Delete", font=('Segoe UI', 9),
                              bg='#e74c3c', fg='white', relief='flat', padx=12, pady=4,
                              command=lambda: self.delete_reminder(reminder['id']))
        delete_btn.pack(side='right', padx=(5, 0))
        
        # Add hover effects
        self.add_hover_effect(card_frame, bg_color, border_color)
    
    def add_hover_effect(self, widget, normal_bg, normal_border):
        def on_enter(event):
            widget.configure(bg=self.darken_color(normal_bg))
        
        def on_leave(event):
            widget.configure(bg=normal_bg)
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def darken_color(self, hex_color):
        # Simple color darkening
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
        # Simplified theme toggle - you can expand this
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
                    # Update notified status in db
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
            
            # Create custom reminder popup
            popup_window = tk.Toplevel(self.root)
            popup_window.title("Medicine Reminder")
            popup_window.geometry("400x300")
            popup_window.configure(bg='#fff3cd')
            popup_window.transient(self.root)
            popup_window.grab_set()
            
            # Center popup
            popup_window.update_idletasks()
            x = (popup_window.winfo_screenwidth() // 2) - (400 // 2)
            y = (popup_window.winfo_screenheight() // 2) - (300 // 2)
            popup_window.geometry(f"400x300+{x}+{y}")
            
            # Popup content
            content_frame = tk.Frame(popup_window, bg='#fff3cd', padx=30, pady=30)
            content_frame.pack(fill='both', expand=True)
            
            # Icon and title
            tk.Label(content_frame, text="💊", font=('Segoe UI', 48), bg='#fff3cd').pack(pady=(0, 10))
            tk.Label(content_frame, text="Time for your medicine!", font=('Segoe UI', 16, 'bold'),
                    bg='#fff3cd', fg='#856404').pack(pady=(0, 20))
            
            # Medicine details
            details_frame = tk.Frame(content_frame, bg='#fff3cd')
            details_frame.pack(pady=(0, 20))
            
            tk.Label(details_frame, text=f"Medicine: {reminder['name']}", font=('Segoe UI', 12, 'bold'),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            tk.Label(details_frame, text=f"Dosage: {reminder['dosage']}", font=('Segoe UI', 12),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            tk.Label(details_frame, text=f"Time: {reminder['time'][-5:]}", font=('Segoe UI', 12),
                    bg='#fff3cd', fg='#856404').pack(anchor='w')
            
            # Action buttons
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