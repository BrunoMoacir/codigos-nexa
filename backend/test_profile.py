from app.analysis.user_profile_analyzer import UserProfileAnalyzer

analyzer = UserProfileAnalyzer()

transactions = [
    {"amount": 7200},
    {"amount": -5300},
]

print(analyzer.run(transactions))
