from uuid import UUID


QLS_SUPPLIER_ID = UUID("00000000-0000-0000-0000-000000000501")
QLS_VERSION_ID = UUID("00000000-0000-0000-0000-000000000502")


QLS_CONFIG = {
    "workbook": {
        "sheetMode": "first",
        "sheetName": None,
        "headerRow": 1,
        "dataStartRow": 2,
    },
    "fields": [
        {
            "key": "parcel_unit_number",
            "name": "Parcel Unit Number",
            "semanticField": "parcel_unit_number",
            "locatorMode": "column",
            "locatorValue": "I",
            "valueType": "text",
            "blankPolicy": "skip_row",
            "caseInsensitive": False,
            "allowUnknownCountry": True,
            "countryAliases": {},
            "constraints": {
                "allowedValues": [],
                "unique": False,
            },
        },
        {
            "key": "destination",
            "name": "Destination",
            "semanticField": "destination",
            "locatorMode": "column",
            "locatorValue": "S",
            "valueType": "country",
            "blankPolicy": "allow",
            "caseInsensitive": True,
            "allowUnknownCountry": True,
            "countryAliases": {},
            "constraints": {"allowedValues": [], "unique": False},
        },
        {
            "key": "number_of_items",
            "name": "Number of Items",
            "semanticField": "number_of_items",
            "locatorMode": "column",
            "locatorValue": "U",
            "valueType": "integer",
            "blankPolicy": "required",
            "caseInsensitive": False,
            "allowUnknownCountry": True,
            "countryAliases": {},
            "constraints": {
                "minValue": "0",
                "maxValue": "20",
                "allowedValues": [],
                "unique": False,
            },
        },
        {
            "key": "weight_kg",
            "name": "Weight KG",
            "semanticField": "weight_kg",
            "locatorMode": "column",
            "locatorValue": "V",
            "valueType": "number",
            "blankPolicy": "required",
            "caseInsensitive": False,
            "allowUnknownCountry": True,
            "countryAliases": {},
            "constraints": {
                "minValue": "0",
                "allowedValues": [],
                "unique": False,
            },
        },
    ],
    "billingGroupColumn": "I",
    "billingDistinctColumn": "I",
}
