from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Category, Transaction, Budget
from .serializers import UserSerializer, CategorySerializer, TransactionSerializer, BudgetSerializer
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from datetime import date, timedelta
import json
import secrets
from django.db.models import Sum
import string
from django.conf import settings
import requests
import openai
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
@login_required
def dashboard(request):
    return render(request, 'finances/dashboard.html')

# Authentication Views
def register_view(request):
    # If user is already authenticated, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        serializer = UserSerializer(data=request.POST)
        if serializer.is_valid():
            user = serializer.save()
            login(request, user)
            return redirect('dashboard')

def login_view(request):
    # If user is already authenticated, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
    
    # Add Google OAuth context
    return render(request, 'finances/login.html', {
        'google_oauth_enabled': hasattr(settings, 'SOCIALACCOUNT_PROVIDERS') and 
                              'google' in settings.SOCIALACCOUNT_PROVIDERS
    })

@login_required
def logout_view(request):
    logout(request)
    return redirect('dashboard')


# API Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_categories(request):
    categories = Category.objects.filter()
    serializer = CategorySerializer(categories, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_category(request):
    data = request.data.copy()
    serializer = CategorySerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transactions(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    serializer = TransactionSerializer(transactions, many=True)
    return Response(serializer.data)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transaction(request, pk):
    try:
        transaction = Transaction.objects.get(pk=pk, user=request.user)  # Verify ownership
        serializer = TransactionSerializer(transaction)
        return Response(serializer.data)
    except Transaction.DoesNotExist:
        return Response(
            {'error': 'Transaction not found or access denied'}, 
            status=404
        )
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_transaction(request):
    serializer = TransactionSerializer(
        data=request.data,
        context={'request': request}  # Pass request for user access
    )
    
    if serializer.is_valid():
        serializer.save()  # User will be auto-set in serializer.create()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_transaction(request, pk):
    try:
        transaction = Transaction.objects.get(pk=pk, user=request.user)
    except Transaction.DoesNotExist:
        return Response(status=404)
    
    serializer = TransactionSerializer(transaction, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)

@api_view(['DELETE'])
def delete_transaction(request, pk):
    try:
        transaction = Transaction.objects.get(pk=pk, user=request.user)
    except Transaction.DoesNotExist:
        return Response(status=404)
    
    # Capture needed info before deletion
    was_expense = transaction.transaction_type == 'expense'
    category = transaction.category
    user = transaction.user
    
    transaction.delete()
    
    if was_expense and category:
        # Recalculate budgets for this category
        update_budget_spent_for_category(user, category)
    
    return Response(status=204)

def update_budget_spent_for_category(user, category):
    """Update all budgets for this user/category combination"""
    budgets = Budget.objects.filter(user=user, category=category)
    for budget in budgets:
        total_spent = Transaction.objects.filter(
            user=user,
            category=category,
            transaction_type='expense',
            date__gte=budget.start_date,
            date__lte=budget.end_date
        ).aggregate(total=Sum('amount'))['total'] or 0
        budget.spent = total_spent
        budget.save()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_budgets(request):
    budgets = Budget.objects.filter(user=request.user)
    serializer = BudgetSerializer(budgets, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_budget(request):
    data = request.data.copy()
    data['user'] = request.user.id

    # Parse necessary fields for filtering transactions
    category_id = data.get('category')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if category_id and start_date and end_date:
        spent = Transaction.objects.filter(
            user=request.user,
            category_id=category_id,
            date__range=[start_date, end_date]
        ).aggregate(total=Sum('amount'))['total'] or 0
        data['spent'] = spent
    serializer = BudgetSerializer(
        data=data,
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def financial_summary(request):
    # Calculate monthly income and expenses
    today = date.today()
    first_day = today.replace(day=1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    income = Transaction.objects.filter(
        user=request.user,
        transaction_type='income',
        date__gte=first_day,
        date__lte=last_day
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__gte=first_day,
        date__lte=last_day
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    savings = income - expenses
    
    # Budget progress
    budgets = Budget.objects.filter(
        user=request.user,
        start_date__lte=today,
        end_date__gte=today
    )
    budget_data = BudgetSerializer(budgets, many=True).data
    
    return Response({
        'income': income,
        'expenses': expenses,
        'savings': savings,
        'budgets': budget_data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    # Default to last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    income_by_category = Transaction.objects.filter(
        user=request.user,
        transaction_type='income',
        date__gte=start_date,
        date__lte=end_date
    ).values('category__name').annotate(total=Sum('amount'))
    
    expenses_by_category = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__gte=start_date,
        date__lte=end_date
    ).values('category__name').annotate(total=Sum('amount'))
    
    # Daily totals
    daily_totals = Transaction.objects.filter(
        user=request.user,
        date__gte=start_date,
        date__lte=end_date
    ).values('date', 'transaction_type').annotate(total=Sum('amount'))
    
    report_data = {
        'income_by_category': list(income_by_category),
        'expenses_by_category': list(expenses_by_category),
        'daily_totals': list(daily_totals),
        'start_date': str(start_date),
        'end_date': str(end_date),
        'ai_report': None
    }
    
    prompt = f"""
    Analyze this financial data and generate a concise 100-word report:
    - Period: {report_data['start_date']} to {report_data['end_date']}
    - Income by category: {report_data['income_by_category']}
    - Expenses by category: {report_data['expenses_by_category']}
    - Daily totals: {report_data['daily_totals']}
    
    The report should:
    1. Highlight key income sources
    2. Identify major expense categories
    3. Note any spending patterns
    4. Provide overall financial health assessment
    5. Be exactly 100 words
    """
    openai.api_key = settings.OPENAI_API_KEY
    # Call OpenAI API
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a financial analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        
        report_data['ai_report'] = response.choices[0].message.content.strip()
        return Response(report_data)
        
    except Exception as e:
        return Response({
            'error': str(e),
            'original_data': report_data
        }, status=500)
def upload_file(request):
    """Handle file uploads to ImgBB with print-based debugging"""
    
    print("\n=== Starting file upload to ImgBB ===")
    
    if 'file' not in request.FILES:
        print("ERROR: No file found in request")
        return JsonResponse({"error": "No file provided"}, status=400)

    file = request.FILES['file']
    print(f"File received: {file.name} ({file.size} bytes, {file.content_type})")

    if file.size > 5 * 1024 * 1024:
        print(f"REJECTED: File too large ({file.size} bytes)")
        return JsonResponse({"error": "File too large (max 5MB)"}, status=400)

    
    allowed_types = ['image/jpeg', 'image/png']
    if file.content_type not in allowed_types:
        print(f"REJECTED: Invalid file type ({file.content_type})")
        return JsonResponse({"error": "Only JPEG, PNG, and PDF files allowed"}, status=400)

    try:
        API_KEY = settings.API_KEY 
        URL= settings.URL
        
        # Read file content
        file_content = file.read()
        def generate_random_filename():
            alphabet = string.ascii_letters + string.digits
            return ''.join(secrets.choice(alphabet) for _ in range(16))

        filename = generate_random_filename()
        # Make the request
        response = requests.post(
            URL,
            params={"key": API_KEY, "expiration": 600},  # 10 minute expiration
            files={"image": (filename, file_content)}
        )
        
        print(f"ImgBB response status: {response.status_code}")
        print(f"Response content: {response.text}")

        if response.status_code != 200:
            raise Exception(f"ImgBB API error: {response.text}")

        result = response.json()
        print("Upload successful!")
        print(f"Image URL: {result['data']['url']}")

        return JsonResponse({
            "success": True,
            "url": result['data']['url'],
            "delete_url": result['data']['delete_url'],
            "format": file.content_type.split('/')[-1],
            "size": file.size
        })

    except Exception as e:
        print("\n!!! UPLOAD FAILED !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        
        return JsonResponse({
            "success": False,
            "error": str(e),
            "debug_info": {
                "file_name": file.name,
                "file_size": file.size,
                "file_type": file.content_type
            }
        }, status=500)
