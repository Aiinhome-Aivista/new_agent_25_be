# Contributing Guidelines

Welcome to the backend project! When contributing code, please follow these guidelines, especially regarding how we write comments.

## Inline Comment Specificity

We believe that code should explain **"What"** it does through clear variable and function naming. Inline comments should be reserved for explaining **"Why"** something was done.

### ❌ Bad Practice (Explaining the "What")
Do not write comments that simply translate the code into English.

```python
# add 1 to x
x = x + 1

# loop through users
for user in users:
    pass
```

### ✅ Good Practice (Explaining the "Why")
Use comments to explain complex logic, workarounds, or magic numbers.

```python
# WORKAROUND: Increment x by 1 to offset the 0-based index from the external API response.
x = x + 1

# We process users in chunks of 50 to avoid hitting the database memory limits during peak hours.
for chunk in get_user_chunks(users, 50):
    pass
```

Always refer to our `Universal_Coding_Standards.json` for all other coding rules.
