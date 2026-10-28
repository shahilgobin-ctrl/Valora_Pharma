from django.core.management.base import BaseCommand
from django.utils.text import slugify

from shop.models import Category, Product


PRODUCTS = [
    ("Amoxicillin", "Infections", "500mg - Capsule", 165, 28, True, "A broad-spectrum antibiotic belonging to the penicillin family, effective against a wide range of bacterial infections."),
    ("Paracetamol", "Pain & Fever", "500mg - Tablet", 45, 100, False, "One of the most widely used and trusted pain relievers and fever reducers available. Gentle and effective."),
    ("Omeprazole", "Digestive Health", "20mg - Capsule", 95, 40, False, "A proton pump inhibitor (PPI) that significantly reduces the amount of acid your stomach produces."),
    ("Metformin", "Diabetes Care", "850mg - Tablet", 125, 35, True, "The most commonly prescribed first-line medication for type 2 diabetes. Helps lower blood sugar."),
    ("Amlodipine", "Heart & Blood Pressure", "5mg - Tablet", 110, 0, True, "A calcium channel blocker used to treat high blood pressure and chest pain."),
    ("Vitamin C", "Vitamins & Supplements", "1000mg - Effervescent", 75, 60, False, "A high-dose effervescent vitamin C supplement that dissolves quickly for easy absorption."),
    ("Ibuprofen", "Pain & Fever", "400mg - Tablet", 55, 45, False, "A non-steroidal anti-inflammatory drug (NSAID) for mild to moderate pain."),
    ("Ciprofloxacin", "Infections", "250mg - Tablet", 245, 20, True, "A fluoroquinolone antibiotic that works by stopping the growth of bacteria."),
    ("Atorvastatin", "Heart & Blood Pressure", "20mg - Tablet", 195, 30, True, "A statin medication that lowers LDL (bad) cholesterol and triglycerides while raising HDL."),
    ("Cetirizine", "Allergies", "10mg - Tablet", 65, 50, False, "A second-generation antihistamine that provides effective, non-drowsy relief from allergies."),
    ("Salbutamol", "Respiratory Care", "100mcg - Inhaler", 285, 25, True, "A fast-acting bronchodilator that relaxes the muscles around the airways."),
    ("Vitamin D3", "Vitamins & Supplements", "5000IU - Softgel", 140, 40, False, "A high-potency vitamin D3 supplement to support bone strength and calcium absorption."),
]

IMAGES = {name: f"/static/shop/products/{slugify(name)}.svg" for name, *_ in PRODUCTS}


class Command(BaseCommand):
    help = "Create or update the 12 ValoraPharma demo shop products."

    def handle(self, *args, **options):
        for name, category_name, strength, price, stock, prescription, description in PRODUCTS:
            category, _ = Category.objects.get_or_create(name=category_name, defaults={"slug": slugify(category_name)})
            Product.objects.update_or_create(
                slug=slugify(name),
                defaults={"name": name, "category": category, "strength": strength, "price": price,
                          "stock_quantity": stock, "is_prescription": prescription,
                          "description": description, "image": IMAGES[name], "is_active": True},
            )
        self.stdout.write(self.style.SUCCESS("Seeded 12 ValoraPharma medicines."))
