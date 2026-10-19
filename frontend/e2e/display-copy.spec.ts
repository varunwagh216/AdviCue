import {test,expect} from '@playwright/test'
import {recordText,reviewExplanation,caseReason} from '../src/lib/display'
test('legacy record labels and raw score fields stay out of advisor copy',()=>{
 const reason="As of 2026-07-31, recorded equity weight is 0.00% and fixed-deposit weight is 55.00%. Pattern rule PAT_PEER_EQ_FD_DEVIATION v2.0. Reported-data triage score 80 ({'summed_negative_gap_pp': '22.42', 'negative_months': 11, 'observed_months': 11, 'gap_points': 35, 'persistence_points': 35, 'assets_points': 10, 'goal_points': 0, 'data_confidence': 'SOURCE_REPORTED'}); not a verified return or suitability conclusion."
 for(const text of [caseReason(reason),recordText(reason),reviewExplanation(reason)]){expect(text).not.toMatch(/PAT_PEER|summed_negative_gap_pp|triage score|\{'/);expect(text).toContain('55')}
 expect(reviewExplanation(reason)).toContain('0% equity')
 expect(recordText('ILLUSTRATIVE DEMO ONLY: Contact investor to confirm allocation and liquidity requirements.')).toBe('Contact investor to confirm allocation and liquidity requirements.')
 expect(recordText('Sample record · Portfolio belongs to a shared review pattern.')).toBe('Portfolio belongs to a shared review pattern.')
 expect(recordText('Contact investor to confirm allocation.')).toBe('Contact investor to confirm allocation.')
})
