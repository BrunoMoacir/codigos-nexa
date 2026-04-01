-- ============================================================
-- Script para popular transações de teste
-- User ID: 4e40074b-cefa-486c-b12c-f1dde2696aea
-- ============================================================

-- Limpar transações existentes dessa conta (se necessário)
DELETE FROM transactions_clean WHERE user_id = '4e40074b-cefa-486c-b12c-f1dde2696aea';

-- ============================================================
-- RECEITAS (Últimos 3 meses)
-- ============================================================

-- Salário (recorrente mensal)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-salary-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Salário Março/2026', 8500.00, '2026-03-05', 'CREDIT', 'Salário', true, false, 'PF', 0.95, false, NULL),
('txn-salary-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Salário Fevereiro/2026', 8500.00, '2026-02-05', 'CREDIT', 'Salário', true, false, 'PF', 0.95, false, NULL),
('txn-salary-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Salário Janeiro/2026', 8500.00, '2026-01-05', 'CREDIT', 'Salário', true, false, 'PF', 0.95, false, NULL);

-- Freelance/Bicos
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-freelance-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Freela Design - Cliente XYZ', 1200.00, '2026-03-15', 'CREDIT', 'Renda Extra', false, false, 'PJ', 0.85, false, 'Serviços'),
('txn-freelance-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Consultoria TI', 2500.00, '2026-02-20', 'CREDIT', 'Renda Extra', false, false, 'PJ', 0.90, false, 'Serviços');

-- ============================================================
-- DESPESAS FIXAS/RECORRENTES
-- ============================================================

-- Aluguel (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-rent-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Aluguel Março', -2800.00, '2026-03-10', 'DEBIT', 'Moradia', true, false, 'PF', 0.98, false, NULL),
('txn-rent-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Aluguel Fevereiro', -2800.00, '2026-02-10', 'DEBIT', 'Moradia', true, false, 'PF', 0.98, false, NULL),
('txn-rent-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Aluguel Janeiro', -2800.00, '2026-01-10', 'DEBIT', 'Moradia', true, false, 'PF', 0.98, false, NULL);

-- Condomínio (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-condo-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Condomínio', -450.00, '2026-03-15', 'DEBIT', 'Moradia', true, false, 'PF', 0.95, false, NULL),
('txn-condo-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Condomínio', -450.00, '2026-02-15', 'DEBIT', 'Moradia', true, false, 'PF', 0.95, false, NULL),
('txn-condo-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Condomínio', -450.00, '2026-01-15', 'DEBIT', 'Moradia', true, false, 'PF', 0.95, false, NULL);

-- Energia (recorrente com variação)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-energy-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'CPFL Energia', -185.50, '2026-03-20', 'DEBIT', 'Contas', true, false, 'PF', 0.90, false, NULL),
('txn-energy-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'CPFL Energia', -172.30, '2026-02-20', 'DEBIT', 'Contas', true, false, 'PF', 0.90, false, NULL),
('txn-energy-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'CPFL Energia', -198.80, '2026-01-20', 'DEBIT', 'Contas', true, false, 'PF', 0.90, false, NULL);

-- Internet (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-internet-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Vivo Fibra 500MB', -119.90, '2026-03-08', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL),
('txn-internet-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Vivo Fibra 500MB', -119.90, '2026-02-08', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL),
('txn-internet-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Vivo Fibra 500MB', -119.90, '2026-01-08', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL);

-- Celular (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-phone-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'TIM Controle', -54.90, '2026-03-12', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL),
('txn-phone-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'TIM Controle', -54.90, '2026-02-12', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL),
('txn-phone-jan-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'TIM Controle', -54.90, '2026-01-12', 'DEBIT', 'Contas', true, false, 'PF', 0.95, false, NULL);

-- Streaming (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-netflix-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Netflix Premium', -55.90, '2026-03-18', 'DEBIT', 'Entretenimento', true, false, 'PF', 0.90, false, NULL),
('txn-netflix-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Netflix Premium', -55.90, '2026-02-18', 'DEBIT', 'Entretenimento', true, false, 'PF', 0.90, false, NULL),
('txn-spotify-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Spotify Premium', -21.90, '2026-03-22', 'DEBIT', 'Entretenimento', true, false, 'PF', 0.90, false, NULL),
('txn-spotify-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Spotify Premium', -21.90, '2026-02-22', 'DEBIT', 'Entretenimento', true, false, 'PF', 0.90, false, NULL);

-- Academia (recorrente)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-gym-mar-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Smart Fit', -89.90, '2026-03-01', 'DEBIT', 'Saúde', true, false, 'PF', 0.92, false, NULL),
('txn-gym-fev-2026', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Smart Fit', -89.90, '2026-02-01', 'DEBIT', 'Saúde', true, false, 'PF', 0.92, false, NULL);

-- ============================================================
-- DESPESAS VARIÁVEIS - SUPERMERCADO
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-market-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Carrefour', -385.60, '2026-03-23', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL),
('txn-market-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Extra Supermercado', -422.30, '2026-03-16', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL),
('txn-market-3', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Pão de Açúcar', -156.90, '2026-03-09', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL),
('txn-market-4', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Carrefour', -398.50, '2026-02-24', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL),
('txn-market-5', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Extra Supermercado', -445.80, '2026-02-17', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL),
('txn-market-6', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Atacadão', -512.40, '2026-02-03', 'DEBIT', 'Alimentação', false, false, 'PF', 0.85, false, NULL);

-- ============================================================
-- RESTAURANTES & DELIVERY
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-ifood-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'iFood - Pizza', -78.90, '2026-03-26', 'DEBIT', 'Alimentação', false, false, 'PF', 0.80, false, NULL),
('txn-ifood-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'iFood - Burguer', -52.50, '2026-03-21', 'DEBIT', 'Alimentação', false, false, 'PF', 0.80, false, NULL),
('txn-rest-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Restaurante Japonês', -185.00, '2026-03-14', 'DEBIT', 'Alimentação', false, false, 'PF', 0.75, false, NULL),
('txn-rest-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Churrascaria Boi na Brasa', -145.00, '2026-03-07', 'DEBIT', 'Alimentação', false, false, 'PF', 0.75, false, NULL),
('txn-ifood-3', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'iFood - Comida Árabe', -65.80, '2026-02-28', 'DEBIT', 'Alimentação', false, false, 'PF', 0.80, false, NULL),
('txn-rest-3', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Café da Manhã - Padaria', -32.50, '2026-02-22', 'DEBIT', 'Alimentação', false, false, 'PF', 0.80, false, NULL);

-- ============================================================
-- TRANSPORTE
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-gas-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Posto Shell - Gasolina', -285.00, '2026-03-25', 'DEBIT', 'Transporte', false, false, 'PF', 0.88, false, NULL),
('txn-gas-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Posto Ipiranga - Gasolina', -298.50, '2026-03-11', 'DEBIT', 'Transporte', false, false, 'PF', 0.88, false, NULL),
('txn-uber-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Uber - Corrida', -28.40, '2026-03-19', 'DEBIT', 'Transporte', false, false, 'PF', 0.85, false, NULL),
('txn-uber-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Uber - Corrida', -35.20, '2026-03-13', 'DEBIT', 'Transporte', false, false, 'PF', 0.85, false, NULL),
('txn-parking-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Estacionamento Shopping', -15.00, '2026-03-14', 'DEBIT', 'Transporte', false, false, 'PF', 0.80, false, NULL);

-- ============================================================
-- COMPRAS & E-COMMERCE
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-amazon-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Amazon - Livros', -89.90, '2026-03-17', 'DEBIT', 'Compras', false, false, 'PF', 0.82, false, NULL),
('txn-merclivre-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Mercado Livre - Eletrônicos', -245.00, '2026-03-10', 'DEBIT', 'Compras', false, false, 'PF', 0.82, false, NULL),
('txn-magazine-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Magazine Luiza - Casa', -156.70, '2026-02-26', 'DEBIT', 'Compras', false, false, 'PF', 0.85, false, NULL);

-- Compra parcelada (notebook)
INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-laptop-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Notebook Dell 1/10', -350.00, '2026-03-05', 'DEBIT', 'Compras', false, true, 'PF', 0.95, false, NULL),
('txn-laptop-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Notebook Dell 2/10', -350.00, '2026-02-05', 'DEBIT', 'Compras', false, true, 'PF', 0.95, false, NULL),
('txn-laptop-3', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Notebook Dell 3/10', -350.00, '2026-01-05', 'DEBIT', 'Compras', false, true, 'PF', 0.95, false, NULL);

-- ============================================================
-- SAÚDE & FARMÁCIA
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-pharmacy-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Drogasil - Medicamentos', -125.80, '2026-03-12', 'DEBIT', 'Saúde', false, false, 'PF', 0.88, false, NULL),
('txn-pharmacy-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Farmácia São Paulo', -67.40, '2026-02-18', 'DEBIT', 'Saúde', false, false, 'PF', 0.88, false, NULL),
('txn-doctor-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Consulta Médica - Dr. Silva', -280.00, '2026-02-15', 'DEBIT', 'Saúde', false, false, 'PF', 0.90, false, NULL);

-- ============================================================
-- INVESTIMENTOS & POUPANÇA
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-invest-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Transferência para Poupança', -1000.00, '2026-03-06', 'DEBIT', 'Investimentos', true, false, 'PF', 0.95, false, NULL),
('txn-invest-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Transferência para Poupança', -1000.00, '2026-02-06', 'DEBIT', 'Investimentos', true, false, 'PF', 0.95, false, NULL),
('txn-invest-3', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Transferência para Poupança', -1000.00, '2026-01-06', 'DEBIT', 'Investimentos', true, false, 'PF', 0.95, false, NULL);

-- ============================================================
-- DESPESAS PJ (Empresa/Negócio)
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-pj-software-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Adobe Creative Cloud', -145.00, '2026-03-08', 'DEBIT', 'Despesas PJ', true, false, 'PJ', 0.92, false, 'Software'),
('txn-pj-software-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'GitHub Pro', -35.00, '2026-03-12', 'DEBIT', 'Despesas PJ', true, false, 'PJ', 0.90, false, 'Software'),
('txn-pj-equip-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Mouse Logitech MX Master', -489.00, '2026-03-02', 'DEBIT', 'Despesas PJ', false, false, 'PJ', 0.88, false, 'Equipamentos'),
('txn-pj-book-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Livro Técnico - OReilly', -125.00, '2026-02-14', 'DEBIT', 'Despesas PJ', false, false, 'PJ', 0.85, false, 'Educação');

-- ============================================================
-- LAZER & ENTRETENIMENTO
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-cinema-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Cinemark - Ingresso', -56.00, '2026-03-22', 'DEBIT', 'Entretenimento', false, false, 'PF', 0.82, false, NULL),
('txn-bar-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Bar do Zé - Happy Hour', -92.50, '2026-03-15', 'DEBIT', 'Entretenimento', false, false, 'PF', 0.75, false, NULL),
('txn-book-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Livraria Cultura', -78.90, '2026-02-28', 'DEBIT', 'Entretenimento', false, false, 'PF', 0.80, false, NULL);

-- ============================================================
-- OUTROS & DIVERSOS
-- ============================================================

INSERT INTO transactions_clean (transaction_id, user_id, account_id, description, amount, date, transaction_type, category, is_recurring, is_installment, context_type, context_confidence, context_override_by_user, pj_subcategory) VALUES
('txn-barber-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Barbeiro - Corte + Barba', -65.00, '2026-03-20', 'DEBIT', 'Cuidados Pessoais', false, false, 'PF', 0.85, false, NULL),
('txn-barber-2', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Barbeiro - Corte + Barba', -65.00, '2026-02-20', 'DEBIT', 'Cuidados Pessoais', false, false, 'PF', 0.85, false, NULL),
('txn-pet-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'PetShop - Ração', -185.00, '2026-03-18', 'DEBIT', 'Pet', false, false, 'PF', 0.88, false, NULL),
('txn-gift-1', '4e40074b-cefa-486c-b12c-f1dde2696aea', 'acc-001', 'Presente Aniversário', -150.00, '2026-03-05', 'DEBIT', 'Outros', false, false, 'PF', 0.70, false, NULL);

-- ============================================================
-- RESUMO DAS TRANSAÇÕES INSERIDAS
-- ============================================================

SELECT
    COUNT(*) as total_transacoes,
    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_receitas,
    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as total_despesas,
    SUM(amount) as saldo_liquido
FROM transactions_clean
WHERE user_id = '4e40074b-cefa-486c-b12c-f1dde2696aea';
