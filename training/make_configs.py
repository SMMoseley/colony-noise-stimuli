import json
import os
import numpy as np
import yaml
import pprint as pp

fp = open('config.yml')
config = yaml.safe_load(fp)

parameters = config['parameters']
stimulus_root = config['stimulus_root']
responses = config['responses']
inversion_map = config['inversion_map']
foreground_data = config['stage_configs']['foreground_data']
background_data = config['stage_configs']['background_data']

reward_archetype = config['reward_archetype']
punish_archetype = config['punish_archetype']
reponse_archetype = config['response_archetype']
stimulus_archetype = config['stimulus_archetype']

class config_file:
    def __init__(self, params, stim_root, responses):
        self.data = {
            'parameters':params,
            'stimulus_root':stim_root,
            'stimuli':[]
        }
        self.responses = responses
    def add_stim(self, stim):
        self.data['stimuli'].append(stim)
    def make_name(self, set_num, fg_dbfs, bg_lvs, invert):
        inv = 'Yes' if invert else 'No'
        snr = '_'.join([str(fg_dbfs-bg_dbfs) for bg_dbfs in bg_lvs])
        self.name = f'2ac-config-snr{snr}-set{set_num}-inverted{inv}'
    def stim_check(self):
        fg_count = {}
        bg_count = {}
        snr_count = {}
        resp_count = {}
        for stim in self.data['stimuli']:
            fg, bg = stim['name'].split('_')
            foreground, fg_lv = fg.split('-')
            background, bg_lv = bg.split('-')
            
            resp = stim['responses']
            for r in self.responses:
                if r not in resp:
                    print(f" - Response {r} not found in {stim['name']}")
                elif 'p_reward' in resp[r]:
                    if r not in resp_count:
                        resp_count[r] = resp[r]['p_reward']
                    else:
                        resp_count[r] += resp[r]['p_reward']
                    if not resp[r]['correct']:
                        print(f" - Rewarded response {r} in {stim['name']} counts as incorrect")
                elif 'p_punish' in resp[r]:
                    if r not in resp_count:
                        resp_count[r] = -resp[r]['p_punish']
                    else:
                        resp_count[r] -= resp[r]['p_punish']
                    if resp[r]['correct']:
                        print(f" - Punished response {r} in {stim['name']} counts as correct")
            
            if foreground not in fg_count:
                fg_count.update({foreground:1})
            else:
                fg_count[foreground] += 1
            
            if background not in bg_count:
                bg_count.update({background:1})
            else:
                bg_count[background] += 1
                
            if f'snr {str(int(bg_lv)-int(fg_lv))}' not in snr_count:
                snr_count.update({f'snr {str(int(bg_lv)-int(fg_lv))}':1})
            else:
                snr_count[f'snr {str(int(bg_lv)-int(fg_lv))}'] += 1
        
        pp.pprint(fg_count)
        pp.pprint(bg_count)
        pp.pprint(snr_count)
        pp.pprint(resp_count)

# invert No/Yes
for invert in [0,1]:
    # set 0/1:
    for set_num,fg_set in enumerate(foreground_data):
        # Initiate config file
        cfg_data = config_file(parameters, stimulus_root, responses)
        
        fg_freq = fg_set['play_freq']
        fg_reward = fg_set['p_reward']
        fg_punish = fg_set['p_punish']
        fg_dbfs = fg_set['dbfs']
        
        cfg_data.make_name(stage, set_num, fg_dbfs, [data['dbfs'] for data in background_data], invert)
        
        print(cfg_data.name, ':')
        # Begin stim add loop:
        for response in responses:
            if response not in fg_set:
                continue
            else:
                # Each foreground stim loop:
                for fg in fg_set[response]:
                    # Each background set (snr) loop:
                    for bg_set in background_data:
                        bg_freq = bg_set['play_freq']
                        bg_dbfs = bg_set['dbfs']
                        bg_reward = bg_set['p_reward']
                        bg_punish = bg_set['p_punish']
                        # Each background stim loop:
                        for bg in bg_set['names']:
                            
                            # Stim name
                            stim_name = f'{fg}{fg_dbfs}_{bg}{bg_dbfs}'
                            # Play frequency multiplier
                            freq = fg_freq * bg_freq
                            
                            stim_data = stimulus_archetype.copy()
                            stim_resp = reponse_archetype.copy()
                            
                            #Determine response which gets rewarded
                            if invert:
                                correct = inversion_map[response]
                            else:
                                correct = response
                                
                            # Write response reward&punish info, with response-specific
                            # and stimuli-specific addition    
                            for r in cfg_data.responses:
                                p_reward = round(cfg_data.responses[r] + fg_reward + bg_reward,1)
                                p_punish = round(cfg_data.responses[r] + fg_punish + bg_punish,1)
                                if r == correct:
                                    reward_data = reward_archetype.copy()
                                    reward_data.update({'p_reward':p_reward})
                                    stim_resp.update({r:reward_data})
                                else:
                                    punish_data = punish_archetype.copy()
                                    punish_data.update({'p_punish':p_punish})
                                    stim_resp.update({r:punish_data})
                                    
                            stim_data.update({
                                'name':stim_name,
                                'frequency':freq,
                                'responses': stim_resp
                            })
                            cfg_data.add_stim(stim_data)
            
        print(f" - Number of stimuli: {len(cfg_data.data['stimuli'])}")
        print(f' - Commencing config check:')
        cfg_data.stim_check()
        print(f' - Config check complete. Writing config to file')
        fname = cfg_data.name + '.json'
        json_data = json.dumps(cfg_data.data, indent=2)
        with open(fname, 'w+') as outfile:
            outfile.write(json_data)