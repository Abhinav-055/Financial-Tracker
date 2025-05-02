from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
class Category(models.Model):
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=[('income', 'Income'), ('expense', 'Expense')])
    
    class Meta:
        unique_together = ( 'name', 'category_type')
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return f"{self.name} ({self.category_type})"

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    date = models.DateField(default=timezone.now)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=10, choices=[('income', 'Income'), ('expense', 'Expense')])
    receipt_url = models.URLField(blank=True, null=True)
    def save(self, *args, **kwargs):
        # Update related budget's spent amount when an expense transaction is saved
        super().save(*args, **kwargs)
        if self.transaction_type == 'expense' and self.category:
            self.update_budget_spent()
    
    def update_budget_spent(self):
        today = timezone.now().date()
        budgets = Budget.objects.filter(
            user=self.user,
            category=self.category,
            start_date__lte=today,
            end_date__gte=today
        )
        for budget in budgets:
            related_expenses = Transaction.objects.filter(
                user=self.user,
                category=self.category,
                transaction_type='expense',
                date__gte=budget.start_date,
                date__lte=budget.end_date
            )
            total_spent = sum(expense.amount for expense in related_expenses)
            print(total_spent)
            if total_spent >  budget.amount: 
                send_mail(
                subject='Budget Limit Warning',
                message=f'You have spent {total_spent} out of your {budget.amount} budget for category {self.category.name}.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.user.email],
                fail_silently=True,
            )
            Budget.objects.filter(pk=budget.pk).update(spent=total_spent)
    
    def __str__(self):
        return f"{self.transaction_type.capitalize()}: {self.amount} on {self.date}"

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    
    class Meta:
        unique_together = ('user', 'category', 'start_date', 'end_date')
    
    @property
    def remaining(self):
        return self.amount - self.spent
    
    @property
    def progress(self):
        if self.amount == 0:
            return 0
        return (self.spent / self.amount) * 100
    
    def __str__(self):
        return f"Budget for {self.category}: {self.amount} ({self.start_date} to {self.end_date})"