"""Decide on interventions
"""
# pylint: disable=C0103
#from digital_comms.mobile_model.ccam import PostcodeSector

import copy
import math
from operator import itemgetter

################################################################
# EXAMPLE COST LOOKUP TABLE
# - TODO come back to net present value or total cost of ownership for costs
################################################################

AVAILABLE_STRATEGY_INTERVENTIONS = {
    # Intervention Strategy 1
    # Minimal Intervention 'Do Nothing Scenario'
    # Build no more additional fibre 
    'minimal': (),

    # Intervention Strategy 2
    'FTTP_most_beneficial_distributions': (),

    # Intervention Strategy 3.
    'FTTP_most_beneficial_cabinets': (),

    # Intervention Strategy 2
    'FTTDP_most_beneficial_distributions': (),

    # Intervention Strategy 3.
    'FTTDP_most_beneficial_cabinets': (),
}

def decide_interventions(strategy, budget, service_obligation_capacity,
                         system, timestep, adoption_cap, telco_match_funding, subsidy):
    """Given strategy parameters and a system return some next best intervention
    """

    # Build to meet demand most beneficial demand
    built, budget, spend, match_funding_spend, subsidised_spend = meet_most_beneficial_demand(
        budget, strategy, timestep, system, adoption_cap, telco_match_funding, subsidy)

    return built, budget, spend, match_funding_spend, subsidised_spend

def meet_most_beneficial_demand(budget, available_interventions, timestep, system, adoption_cap, telco_match_funding, subsidy):
    return _suggest_interventions(
        budget, available_interventions, system, timestep, adoption_cap, telco_match_funding, subsidy)


def _suggest_interventions(budget, strategy, system, timestep, adoption_cap, telco_match_funding, subsidy, threshold=None):
    built_interventions = []
    spend = []
    match_funding_spend = []
    premises_passed = 0
    subsidised_spend = []

    if strategy == 'fttp_rollout_per_distribution':
        distributions = sorted(system._distributions, key=lambda item: item.rollout_bcr['fttp']) 
        for distribution in distributions:
            if (premises_passed + len(distribution._clients)) < adoption_cap:
                if distribution.rollout_costs['fttp'] < budget:
                    budget -= distribution.rollout_costs['fttp']
                    built_interventions.append((distribution.id, 'rollout_fttp', distribution.rollout_costs['fttp']))
                    spend.append((distribution.id, strategy, distribution.rollout_costs['fttp']))
                    premises_passed += len(distribution._clients)
                else:
                    break
            else:
                break

    elif strategy == 'fttp_subsidised_rollout_per_distribution':
        market_based_distributions = sorted(system._distributions, key=lambda item: True if item.rollout_bcr['fttp'] > 1 == 0 else False, reverse=True)      
        for distribution in market_based_distributions:
            if (premises_passed + len(distribution._clients)) < adoption_cap:
                if distribution.rollout_costs['fttp'] < budget:
                    budget -= distribution.rollout_costs['fttp']
                    built_interventions.append((distribution.id, 'rollout_fttp', distribution.rollout_costs['fttp']))
                    spend.append((distribution.id, strategy, distribution.rollout_costs['fttp']))
                    premises_passed += len(distribution._clients)
                else:
                    break
            else:
                break
        
        subsidised_distributions = sorted(system._distributions, key=lambda item: True if item.rollout_bcr['fttp'] < 1 == 0 else False, reverse=True)
        # subsidy_cutoff = math.floor(len(subsidised_distributions) * 0.66) # get the bottom third of the distribution cutoff point
        # subsidised_distributions = subsidised_distributions[subsidy_cutoff:] # get the bottom third of the distribution
        for distribution in subsidised_distributions:
            if distribution.rollout_costs['fttp'] < telco_match_funding:
                subsidy_required_per_distribution_point = distribution.rollout_costs['fttp'] - distribution.rollout_benefits['fttp']
                telco_match_funding -= distribution.rollout_costs['fttp']
                distribution.rollout_costs['fttp'] = distribution.rollout_costs['fttp'] + subsidy_required_per_distribution_point               
                built_interventions.append((distribution.id, 'subsidised_fttp', distribution.rollout_costs['fttp']))
                match_funding_spend.append((distribution.id, strategy, distribution.rollout_costs['fttp']))
                subsidised_spend.append((distribution.id, strategy, distribution.rollout_costs['fttp'], subsidy_required_per_distribution_point))
                premises_passed += len(distribution._clients)
            else:
                break

    elif strategy == 'fttdp_rollout_per_distribution':
        distributions = sorted(system._distributions, key=lambda item: True if item.rollout_bcr['fttdp'] > 1 == 0 else False, reverse=True)
        for distribution in distributions:
            if (premises_passed + len(distribution._clients)) < adoption_cap:
                if distribution.rollout_costs['fttdp'] < budget:
                    budget -= distribution.rollout_costs['fttdp']
                    built_interventions.append((distribution.id, 'rollout_fttdp', distribution.rollout_costs['fttdp']))
                    spend.append((distribution.id, strategy, distribution.rollout_costs['fttdp']))
                    premises_passed += len(distribution._clients)
                else:
                    break
            else:
                break
        
    elif strategy == 'fttdp_subsidised_rollout_per_distribution':
        market_based_distributions = sorted(system._distributions, key=lambda item: True if item.rollout_bcr['fttdp'] > 1 == 0 else False, reverse=True)
        for distribution in market_based_distributions:
            if (premises_passed + len(distribution._clients)) < adoption_cap:
                if distribution.rollout_costs['fttdp'] < budget:
                    budget -= distribution.rollout_costs['fttdp']
                    built_interventions.append((distribution.id, 'rollout_fttdp', distribution.rollout_costs['fttdp']))
                    spend.append((distribution.id, strategy, distribution.rollout_costs['fttdp']))
                    premises_passed += len(distribution._clients)
                else:
                    break
            else:
                break
        
        subsidised_distributions = sorted(system._distributions, key=lambda item: True if item.rollout_bcr['fttdp'] < 1 == 0 else False, reverse=True)
        # subsidy_cutoff = math.floor(len(subsidised_distributions) * 0.66) # get the bottom third of the distribution cutoff point
        # subsidised_distributions = subsidised_distributions[subsidy_cutoff:] # get the bottom third of the distribution
        for distribution in subsidised_distributions:
            if distribution.rollout_costs['fttdp'] < telco_match_funding:
                subsidy_required_per_distribution_point = distribution.rollout_costs['fttdp'] - distribution.rollout_benefits['fttdp']
                telco_match_funding -= distribution.rollout_costs['fttdp']
                distribution.rollout_costs['fttdp'] = distribution.rollout_costs['fttdp'] + subsidy_required_per_distribution_point               
                built_interventions.append((distribution.id, 'subsidised_fttdp', distribution.rollout_costs['fttdp']))
                match_funding_spend.append((distribution.id, strategy, distribution.rollout_costs['fttdp']))
                subsidised_spend.append((distribution.id, strategy, distribution.rollout_costs['fttdp'], subsidy_required_per_distribution_point))
                premises_passed += len(distribution._clients)
            else:
                break

    return built_interventions, budget, spend, match_funding_spend, subsidised_spend