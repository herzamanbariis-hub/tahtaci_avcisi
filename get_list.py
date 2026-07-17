import ast
with open('data_ingestion.py', 'r', encoding='utf-8') as f:
    for node in ast.walk(ast.parse(f.read())):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'BIST_STOCKS':
                    print(ast.literal_eval(node.value))
