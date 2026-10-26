"""Fictional training inventory. MUR prices are per selling unit, not market quotes.

Tablets/capsules are sold individually; topical products and inhalers are sold
as one container/device. Prescription flags are application scenarios, not a
statement of local dispensing law. No dosing instructions are supplied.
"""

CATALOGUE = [
    ("Paracetamol", "500 mg", "Tablet", "Pain relief", False, "3.50"),
    ("Ibuprofen", "200 mg", "Tablet", "Pain relief", False, "4.25"),
    ("Cetirizine", "10 mg", "Tablet", "Allergy", False, "5.50"),
    ("Loratadine", "10 mg", "Tablet", "Allergy", False, "5.00"),
    ("Oral Rehydration Salts", "Standard sachet", "Powder", "Hydration", False, "7.50"),
    ("Saline Nasal Spray", "0.9%", "Spray", "Nasal care", False, "145.00"),
    ("Antacid", "500 mg", "Chewable Tablet", "Digestive care", False, "3.75"),
    ("Vitamin C", "500 mg", "Tablet", "Vitamins", False, "6.00"),
    ("Zinc", "20 mg", "Tablet", "Vitamins", False, "4.90"),
    ("Clotrimazole", "1%", "Cream", "Skin care", False, "125.00"),
    ("Calamine Lotion", "100 ml", "Lotion", "Skin care", False, "150.00"),
    ("Glycerin", "100 ml", "Solution", "Skin care", False, "90.00"),
    ("Throat Lozenges", "Standard", "Lozenge", "Cold and flu", False, "4.00"),
    ("Vitamin D", "400 IU", "Tablet", "Vitamins", False, "8.50"),
    ("Petroleum Jelly", "100 g", "Ointment", "Skin care", False, "100.00"),
    ("Amoxicillin", "500 mg", "Capsule", "Antibiotic", True, "14.00"),
    ("Metformin", "500 mg", "Tablet", "Diabetes", True, "8.00"),
    ("Amlodipine", "5 mg", "Tablet", "Cardiovascular", True, "9.00"),
    ("Atorvastatin", "20 mg", "Tablet", "Cardiovascular", True, "11.00"),
    ("Omeprazole", "20 mg", "Capsule", "Digestive care", True, "7.50"),
    ("Losartan", "50 mg", "Tablet", "Cardiovascular", True, "10.50"),
    ("Doxycycline", "100 mg", "Capsule", "Antibiotic", True, "13.00"),
    ("Levothyroxine", "50 mcg", "Tablet", "Endocrine", True, "6.50"),
    ("Salbutamol Inhaler", "100 mcg/dose", "Inhaler", "Respiratory", True, "350.00"),
    ("Gliclazide", "80 mg", "Tablet", "Diabetes", True, "12.00"),
]

CUSTOMERS = [
    ("Anjali", "Raman"),
    ("Kevin", "Morel"),
    ("Aisha", "Dawood"),
    ("Nicolas", "Laurent"),
    ("Priya", "Seewoo"),
    ("Yusuf", "Adam"),
    ("Emma", "Hoarau"),
    ("Ravi", "Nair"),
    ("Sarah", "Chan"),
    ("Dylan", "Payet"),
    ("Meera", "Pillay"),
    ("Adam", "Joseph"),
    ("Chloe", "Wong"),
    ("Sameer", "Ali"),
    ("Lea", "Robert"),
    ("Kiran", "Ramsamy"),
    ("Sonia", "Lee"),
    ("Marc", "Duval"),
]

SUPPLIERS = (
    "Lagoon Medical Distribution (fictional)",
    "Central Healthcare Supply (fictional)",
    "Island Pharmaceutical Logistics (fictional)",
)


SELLING_UNITS = {
    "Tablet": "tablet",
    "Capsule": "capsule",
    "Powder": "sachet",
    "Spray": "bottle",
    "Chewable Tablet": "tablet",
    "Cream": "tube",
    "Lotion": "bottle",
    "Solution": "bottle",
    "Lozenge": "lozenge",
    "Ointment": "jar",
    "Inhaler": "inhaler",
}
