from django.core.exceptions import ValidationError

def validate_cedula_ec(value):
    if not value.isdigit():
        raise ValidationError(
            'The ID must contain only numbers.',
            code='invalid_chars'
        )

    if len(value) not in (10, 13):
        raise ValidationError(
            'The ID must be 10 digits (cédula) or 13 digits (RUC).',
            code='invalid_length'
        )

    province = int(value[:2])
    if province < 1 or province > 24:
        raise ValidationError(
            f'Invalid province code: {province}. Must be between 01 and 24.',
            code='invalid_province'
        )

    third_digit = int(value[2])
    if third_digit >= 6:
        raise ValidationError(
            'The third digit must be less than 6 for natural persons.',
            code='invalid_third'
        )

    coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i in range(9):
        result = int(value[i]) * coefficients[i]
        if result > 9:
            result -= 9
        total += result

    verifier = 10 - (total % 10)
    if verifier == 10:
        verifier = 0

    if verifier != int(value[9]):
        raise ValidationError(
            'Invalid ID number. The check digit does not match.',
            code='invalid_verifier'
        )

    return value