from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('markets', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='market',
            old_name='first_result_time',
            new_name='open_time',
        ),
        migrations.RenameField(
            model_name='market',
            old_name='second_result_time',
            new_name='close_time',
        ),
        migrations.AlterField(
            model_name='market',
            name='open_time',
            field=models.TimeField(help_text='Open Result Time (HH:MM)'),
        ),
        migrations.AlterField(
            model_name='market',
            name='close_time',
            field=models.TimeField(help_text='Close Result Time (HH:MM)'),
        ),
        migrations.AlterField(
            model_name='result',
            name='result_type',
            field=models.CharField(choices=[('OPEN', 'Open Result'), ('CLOSE', 'Close Result')], max_length=10),
        ),
        migrations.AlterField(
            model_name='fetchattempt',
            name='result_type',
            field=models.CharField(choices=[('OPEN', 'Open Result'), ('CLOSE', 'Close Result')], max_length=10),
        ),
    ]
