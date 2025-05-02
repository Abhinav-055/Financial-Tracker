from rest_framework import serializers
from django.contrib.auth.models import User
import logging
from .models import Category, Transaction, Budget
import os
#
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'category_type']
    
    def validate(self, data):
        # Ensure the user doesn't have duplicate category names for the same type
        if Category.objects.filter( name=data['name'], category_type=data['category_type']).exists():
            raise serializers.ValidationError("You already have a category with this name and type.")
        return data

# finances/serializers.py
class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'date', 'description', 'category', 'category_name', 'transaction_type','receipt_url']
        extra_kwargs = {
            'user': {'read_only': True}  # Prevent user from being set via API
        }
    
    def create(self, validated_data):
        # Automatically set the user from the request
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    
    def validate(self, data):
        # Your existing validation logic
        if 'category' in data and data['category']:
            if data['category'].category_type != data.get('transaction_type'):
                raise serializers.ValidationError("Category type must match transaction type.")
        return data

class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    remaining = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    progress = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Budget
        fields = ['id', 'category', 'category_name', 'amount', 'spent', 'remaining', 'progress', 'start_date', 'end_date']
        extra_kwargs = {
            'user': {'read_only': True}  # Prevent user from being set via API
        }
    def create(self, validated_data):
        # Automatically set the user from the request
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def validate(self, data):
        # Ensure the category is an expense category
        if 'category' in data and data['category'].category_type != 'expense':
            raise serializers.ValidationError("Budget can only be set for expense categories.")
        
        # Ensure date range is valid
        if 'start_date' in data and 'end_date' in data and data['start_date'] > data['end_date']:
            raise serializers.ValidationError("End date must be after start date.")
        
        return data