from django.db import models

class AppPage(models.Model):
    PAGE_CHOICES = (
        ('privacy_policy', 'Privacy Policy'),
        ('terms_conditions', 'Terms & Conditions'),
        ('about_us', 'About Us'),
    )
    
    slug = models.CharField(max_length=50, choices=PAGE_CHOICES, unique=True)
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="HTML content for the page")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_slug_display()