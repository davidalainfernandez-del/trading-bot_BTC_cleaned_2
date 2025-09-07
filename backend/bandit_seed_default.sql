-- bandit_seed_default.sql
INSERT OR IGNORE INTO bandit_arms(id,pulls,reward_sum,last_update,cfg_json) VALUES
 ('FREQ_56',0,0.0,strftime('%s','now'),'{"PBUY":0.56,"PSELL":0.44,"MIN_EV_NET":0.00015}'),
 ('FREQ_58',0,0.0,strftime('%s','now'),'{"PBUY":0.58,"PSELL":0.42,"MIN_EV_NET":0.00020}'),
 ('BAL_60', 0,0.0,strftime('%s','now'),'{"PBUY":0.60,"PSELL":0.40,"MIN_EV_NET":0.00025}'),
 ('EDGE_62',0,0.0,strftime('%s','now'),'{"PBUY":0.62,"PSELL":0.38,"MIN_EV_NET":0.00030}');
