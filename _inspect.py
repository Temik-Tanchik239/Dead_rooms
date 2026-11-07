lines = open('data/skills.json', encoding='utf-8').read().splitlines()
print('\n'.join(f'{j+1}: {lines[j]}' for j in range(max(0, len(lines) - 30), len(lines))))
