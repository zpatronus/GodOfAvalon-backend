# Generated by Django 4.0.3 on 2022-03-31 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('room', '0002_remove_room_roompsw'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('roomid', models.CharField(max_length=6)),
                ('userid', models.CharField(max_length=6)),
                ('userpsw', models.CharField(max_length=6)),
            ],
        ),
    ]