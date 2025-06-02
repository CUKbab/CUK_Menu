import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import json
import os

class JSONMenuEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("JSON Menu Editor")

        self.data = {}
        self.file_path = None

        self.setup_ui()

    def setup_ui(self):
        # Buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill="x")

        tk.Button(button_frame, text="Open JSON", command=self.load_json).pack(side="left")
        tk.Button(button_frame, text="Save JSON", command=self.save_json).pack(side="left")
        tk.Button(button_frame, text="Add Item", command=self.add_item).pack(side="left")
        tk.Button(button_frame, text="Remove Item", command=self.remove_item).pack(side="left")

        # Treeview
        self.tree = ttk.Treeview(self.root)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.edit_item)

        self.tree["columns"] = ("value",)
        self.tree.column("#0", width=200)
        self.tree.heading("#0", text="Day/Menu")
        self.tree.column("value", width=300)
        self.tree.heading("value", text="Menu Item")

    def load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.file_path = path
        self.populate_tree()

    def save_json(self):
        if not self.file_path:
            self.file_path = filedialog.asksaveasfilename(defaultextension=".json")
        if not self.file_path:
            return
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        messagebox.showinfo("Saved", f"Saved to {os.path.basename(self.file_path)}")

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        for category, days in self.data.items():
            cat_id = self.tree.insert("", "end", text=category, open=True)
            for day, items in days.items():
                day_id = self.tree.insert(cat_id, "end", text=day, open=True)
                for item in items:
                    self.tree.insert(day_id, "end", text="", values=(item,))

    def add_item(self):
        selected = self.tree.focus()
        if not selected:
            return

        parent = self.tree.parent(selected)
        if parent == "":
            messagebox.showwarning("Select Day", "Please select a day to add the item.")
            return

        if self.tree.parent(parent) == "":
            day_id = selected
            cat_id = parent
        else:
            day_id = parent
            cat_id = self.tree.parent(parent)

        cat = self.tree.item(cat_id)["text"]
        day = self.tree.item(day_id)["text"]

        new_item = simpledialog.askstring("Add Menu Item", "Enter menu item:")
        if new_item:
            self.data[cat][day].append(new_item)
            self.tree.insert(day_id, "end", text="", values=(new_item,))

    def remove_item(self):
        selected = self.tree.focus()
        parent = self.tree.parent(selected)
        if parent and self.tree.parent(parent):
            cat_id = self.tree.parent(parent)
            day_id = parent
            item_text = self.tree.item(selected)["values"][0]
            cat = self.tree.item(cat_id)["text"]
            day = self.tree.item(day_id)["text"]
            self.data[cat][day].remove(item_text)
            self.tree.delete(selected)
        else:
            messagebox.showwarning("Invalid Selection", "Select a menu item to remove.")

    def edit_item(self, event):
        selected = self.tree.focus()
        parent = self.tree.parent(selected)
        if parent and self.tree.parent(parent):
            cat_id = self.tree.parent(parent)
            day_id = parent
            old_value = self.tree.item(selected)["values"][0]
            new_value = simpledialog.askstring("Edit Menu Item", "Edit menu item:", initialvalue=old_value)
            if new_value and new_value != old_value:
                cat = self.tree.item(cat_id)["text"]
                day = self.tree.item(day_id)["text"]
                idx = self.data[cat][day].index(old_value)
                self.data[cat][day][idx] = new_value
                self.tree.item(selected, values=(new_value,))

if __name__ == "__main__":
    root = tk.Tk()
    app = JSONMenuEditor(root)
    root.mainloop()
