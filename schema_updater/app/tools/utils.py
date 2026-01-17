registry = [
  {
    "name": "Vehicle",
    "description": "Основна сутність для обліку транспортних засобів, технічних характеристик та реєстраційних даних",
    "fields": [
      {
        "name": "brand",
        "description": "Марка автомобіля (наприклад, SKODA, TOYOTA)",
        "type": "string",
        "nullable": False
      },
      {
        "name": "model",
        "description": "Конкретна модель транспортного засобу",
        "type": "string",
        "nullable": False
      },
      {
        "name": "vin_code",
        "description": "Унікальний ідентифікаційний номер кузова (VIN)",
        "type": "string",
        "nullable": False
      },
      {
        "name": "production_year",
        "description": "Рік випуску автомобіля",
        "type": "integer",
        "nullable": False
      },
      {
        "name": "color",
        "description": "Колір кузова згідно з техпаспортом",
        "type": "string",
        "nullable": False
      }
    ]
  },
  {
    "name": "LegalEntity",
    "description": "Дані про юридичних осіб (компанії), що володіють активами",
    "fields": [
      {
        "name": "company_name",
        "description": "Офіційна назва організації",
        "type": "string",
        "nullable": False
      },
      {
        "name": "edrpou",
        "description": "Код ЄДРПОУ (8 цифр)",
        "type": "string",
        "nullable": False
      }
    ]
  }
]