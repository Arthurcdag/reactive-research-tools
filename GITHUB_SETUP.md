# GitHub setup

The repository package is ready to push.

## Option A: GitHub CLI

From inside this folder:

```bash
git init
git add .
git commit -m "Initial research toolchain"

gh repo create Arthurcdag/reactive-research-tools --private --source . --remote origin --push
```

For public:

```bash
gh repo create Arthurcdag/reactive-research-tools --public --source . --remote origin --push
```

## Option B: GitHub website

1. Go to https://github.com/new
2. Create a repository named `reactive-research-tools`
3. Do not initialize it with a README, since this package already has one.
4. From this folder run:

```bash
git init
git add .
git commit -m "Initial research toolchain"
git branch -M main
git remote add origin https://github.com/Arthurcdag/reactive-research-tools.git
git push -u origin main
```

## Note

I did not push this automatically because no target repository was specified and I should not overwrite an existing unrelated repository.
