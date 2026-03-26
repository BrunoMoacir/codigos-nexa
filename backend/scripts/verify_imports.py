#!/usr/bin/env python3
"""
verify_all_imports.py - Verificador de Imports do Projeto

OBJETIVO:
    Testar TODOS os imports de TODOS os módulos Python do projeto
    para garantir que não há dependências quebradas.

EXECUÇÃO:
    cd /Users/gabriel-abel/projetoNexa/codigos-nexa-9/backend
    python verify_all_imports.py

SAÍDA:
    ✅ Módulos que importam com sucesso
    ❌ Módulos com erros de import
    📊 Estatísticas finais
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple, Dict
import importlib.util
import traceback

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Adicionar backend ao path
current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Diretórios a verificar
DIRS_TO_CHECK = [
    "app/api",
    "app/agent",
    "app/analysis",
    "app/cashflow",
    "app/core",
    "app/domain",
    "app/etl",
    "app/integrations",
    "app/schemas",
    "tests",
]

# Arquivos a ignorar
IGNORE_PATTERNS = [
    "__pycache__",
    ".pyc",
    ".pyo",
    ".git",
    "venv",
    "env",
    ".pytest_cache",
    "node_modules",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def should_ignore(path: Path) -> bool:
    """Verifica se arquivo/diretório deve ser ignorado."""
    return any(pattern in str(path) for pattern in IGNORE_PATTERNS)


def find_python_files(base_dir: Path, subdirs: List[str]) -> List[Path]:
    """
    Encontra todos os arquivos Python no projeto.
    
    Args:
        base_dir: Diretório base (backend/)
        subdirs: Lista de subdiretórios a verificar
    
    Returns:
        Lista de arquivos .py encontrados
    """
    python_files = []
    
    for subdir in subdirs:
        full_path = base_dir / subdir
        
        if not full_path.exists():
            print(f"⚠️  Diretório não encontrado: {subdir}")
            continue
        
        # Buscar recursivamente por .py
        for py_file in full_path.rglob("*.py"):
            if not should_ignore(py_file):
                python_files.append(py_file)
    
    return sorted(python_files)


def import_module_from_file(file_path: Path, base_dir: Path) -> Tuple[bool, str]:
    """
    Tenta importar um módulo Python.
    
    Args:
        file_path: Caminho do arquivo .py
        base_dir: Diretório base do projeto
    
    Returns:
        (success: bool, error_message: str)
    """
    try:
        # Converter caminho para nome de módulo
        # Ex: backend/app/core/recurrence.py → app.core.recurrence
        relative_path = file_path.relative_to(base_dir)
        module_name = str(relative_path.with_suffix("")).replace(os.sep, ".")
        
        # Tentar importar
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return False, f"Não foi possível criar spec para {module_name}"
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        return True, ""
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, error_msg


def categorize_error(error_msg: str) -> str:
    """Categoriza o tipo de erro."""
    if "ModuleNotFoundError" in error_msg:
        if "No module named 'app'" in error_msg:
            return "PYTHONPATH"
        else:
            return "DEPENDÊNCIA_FALTANDO"
    elif "ImportError" in error_msg:
        return "IMPORT_QUEBRADO"
    elif "SyntaxError" in error_msg:
        return "SYNTAX_ERROR"
    elif "AttributeError" in error_msg:
        return "ATRIBUTO_FALTANDO"
    else:
        return "OUTRO"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERIFICAÇÃO PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Executa verificação de todos os imports."""
    
    print("=" * 80)
    print("🔍 VERIFICAÇÃO DE IMPORTS - NEXA AI")
    print("=" * 80)
    print(f"\n📂 Diretório base: {current_dir}")
    print(f"🐍 Python: {sys.version.split()[0]}")
    print(f"📍 Executável: {sys.executable}\n")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ENCONTRAR ARQUIVOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("📋 Procurando arquivos Python...")
    python_files = find_python_files(current_dir, DIRS_TO_CHECK)
    print(f"   Encontrados: {len(python_files)} arquivos\n")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TESTAR IMPORTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("🧪 Testando imports...\n")
    
    results = {
        "success": [],
        "failed": [],
    }
    
    errors_by_category: Dict[str, List[Tuple[Path, str]]] = {
        "PYTHONPATH": [],
        "DEPENDÊNCIA_FALTANDO": [],
        "IMPORT_QUEBRADO": [],
        "SYNTAX_ERROR": [],
        "ATRIBUTO_FALTANDO": [],
        "OUTRO": [],
    }
    
    for i, py_file in enumerate(python_files, 1):
        relative_path = py_file.relative_to(current_dir)
        
        # Mostrar progresso
        progress = f"[{i}/{len(python_files)}]"
        
        success, error = import_module_from_file(py_file, current_dir)
        
        if success:
            results["success"].append(py_file)
            print(f"   ✅ {progress} {relative_path}")
        else:
            results["failed"].append((py_file, error))
            category = categorize_error(error)
            errors_by_category[category].append((py_file, error))
            print(f"   ❌ {progress} {relative_path}")
            print(f"      → {error[:100]}...")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ESTATÍSTICAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "=" * 80)
    print("📊 ESTATÍSTICAS")
    print("=" * 80)
    
    total = len(python_files)
    success_count = len(results["success"])
    failed_count = len(results["failed"])
    success_rate = (success_count / total * 100) if total > 0 else 0
    
    print(f"\n✅ Sucesso:  {success_count}/{total} ({success_rate:.1f}%)")
    print(f"❌ Falhou:   {failed_count}/{total} ({100-success_rate:.1f}%)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BREAKDOWN POR CATEGORIA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if failed_count > 0:
        print("\n" + "=" * 80)
        print("🔍 ERROS POR CATEGORIA")
        print("=" * 80)
        
        for category, errors in errors_by_category.items():
            if errors:
                print(f"\n📌 {category} ({len(errors)} erros):")
                for py_file, error in errors[:5]:  # Mostrar primeiros 5
                    relative = py_file.relative_to(current_dir)
                    print(f"   • {relative}")
                    print(f"     {error[:80]}...")
                
                if len(errors) > 5:
                    print(f"   ... e mais {len(errors) - 5} erros")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RECOMENDAÇÕES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if failed_count > 0:
        print("\n" + "=" * 80)
        print("💡 RECOMENDAÇÕES")
        print("=" * 80)
        
        if errors_by_category["PYTHONPATH"]:
            print("\n🔧 PYTHONPATH:")
            print("   Crie conftest.py em todos os diretórios com testes")
            print("   Exemplo: backend/conftest.py, backend/app/conftest.py")
        
        if errors_by_category["DEPENDÊNCIA_FALTANDO"]:
            print("\n📦 DEPENDÊNCIAS FALTANDO:")
            print("   Execute: pip install -r requirements.txt")
            print("   Ou instale manualmente:")
            
            # Extrair nomes de módulos faltando
            missing_modules = set()
            for _, error in errors_by_category["DEPENDÊNCIA_FALTANDO"]:
                if "No module named" in error:
                    # Extrair nome do módulo
                    parts = error.split("'")
                    if len(parts) >= 2:
                        module_name = parts[1].split(".")[0]
                        missing_modules.add(module_name)
            
            for module in sorted(missing_modules):
                print(f"   • pip install {module}")
        
        if errors_by_category["IMPORT_QUEBRADO"]:
            print("\n🔨 IMPORTS QUEBRADOS:")
            print("   Revise os imports nos arquivos listados acima")
            print("   Verifique se funções/classes existem nos módulos")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONCLUSÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "=" * 80)
    
    if failed_count == 0:
        print("✅ TODOS OS IMPORTS ESTÃO CORRETOS!")
        print("=" * 80)
        print("\n🎉 Projeto pronto para produção!\n")
        return 0
    else:
        print("❌ ALGUNS IMPORTS ESTÃO QUEBRADOS!")
        print("=" * 80)
        print(f"\n⚠️  Corrija os {failed_count} erros antes de prosseguir.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())