from app.analysis.user_profile_analyzer import UserProfileAnalyzer

transactions = [
    {"amount": 7200},
    {"amount": -5300},
]

analyzer = UserProfileAnalyzer()
print(analyzer.run(transactions))
