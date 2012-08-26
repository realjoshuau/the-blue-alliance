import json
import logging

from BeautifulSoup import BeautifulSoup

from datafeeds.datafeed_helper import recurseUntilString
from datafeeds.datafeed_parser_base import DatafeedParserBase

class UsfirstMatchesParser(DatafeedParserBase):
    @classmethod
    def parse(self, html):
        """
        Parse the table that contains qualification match results.
        """
        matches = list()
        soup = BeautifulSoup(html,
                convertEntities=BeautifulSoup.HTML_ENTITIES)
        
        tables = soup.findAll('table')
        
        matches.extend(self.parseQualMatchResultList(tables[2]))
        matches.extend(self.parseElimMatchResultList(tables[2]))
        matches.extend(self.parseElimMatchResultList(tables[3]))

        return matches

    @classmethod
    def parseQualMatchResultList(self, table):
        matches = list()
        for tr in table.findAll('tr')[2:]:
            tds = tr.findAll('td')
            if len(tds) == 10:
                if recurseUntilString(tds[1]) is not None:
                    red_teams = ["frc" + recurseUntilString(tds[2]), "frc" + recurseUntilString(tds[3]), "frc" + recurseUntilString(tds[4])]
                    blue_teams = ["frc" + recurseUntilString(tds[5]), "frc" + recurseUntilString(tds[6]), "frc" + recurseUntilString(tds[7])]
                    
                    try:
                        if tds[8].string == None:
                            red_score = -1
                        else:
                            red_score = int(recurseUntilString(tds[8]))
                    
                        if tds[9].string == None:
                            blue_score = -1
                        else:
                            blue_score = int(recurseUntilString(tds[9]))
                        
                        match_number = int(recurseUntilString(tds[1]))

                        alliances = {
                            "red": {
                                "teams": red_teams,
                                "score": red_score
                            },
                            "blue": {
                                "teams": blue_teams,
                                "score": blue_score
                            }
                        }
                        
                        matches.append({
                            "alliances_json": json.dumps(alliances),
                            "comp_level": "qm",
                            "match_number": match_number,
                            "set_number": 1,
                            "team_key_names": red_teams + blue_teams,
                            })

                    except Exception, detail:
                        logging.info('Match Parse Failed: ' + str(detail))
        
        return matches

    @classmethod
    def parseElimMatchResultList(self, table):
        """
        Parse the table that contains elimination match results.
        """
        matches = list()
        for tr in table.findAll('tr')[2:]:
            tds = tr.findAll('td')
            if len(tds) == 11:
                if recurseUntilString(tds[1]) is not None:
                    red_teams = ["frc" + recurseUntilString(tds[3]), "frc" + recurseUntilString(tds[4]), "frc" + recurseUntilString(tds[5])]
                    blue_teams = ["frc" + recurseUntilString(tds[6]), "frc" + recurseUntilString(tds[7]), "frc" + recurseUntilString(tds[8])]
                    
                    try:
                        if recurseUntilString(tds[9]) == None:
                            red_score = -1
                        else:
                            red_score = int(recurseUntilString(tds[9]))
                        
                        if recurseUntilString(tds[10]) == None:
                            blue_score = -1
                        else:
                            blue_score = int(recurseUntilString(tds[10]))
                        
                        match_number_info = self.parseElimMatchNumberInfo(recurseUntilString(tds[1]))
                    
                        alliances = {
                            "red": {
                                "teams": red_teams,
                                "score": red_score
                            },
                            "blue": {
                                "teams": blue_teams,
                                "score": blue_score
                            }
                        }
                        
                        # Don't write down uncompleted elimination matches
                        if (red_score > -1 and blue_score > -1):
                            matches.append({
                                "alliances_json": json.dumps(alliances),
                                "comp_level": match_number_info["comp_level"],
                                "match_number": match_number_info["match_number"],
                                "set_number": match_number_info["set_number"],
                                "team_key_names": red_teams + blue_teams,
                            })

                    except Exception, detail:
                        logging.info('Match Parse Failed: ' + str(detail))    
        
        return matches
    
    @classmethod 
    def parseElimMatchNumberInfo(self, string):
        """
        Parse out the information about an elimination match based on the
        string USFIRST provides.
        They look like "Semi 2-2"
        """
        comp_level_dict = {
            "Qtr": "qf",
            "Semi": "sf",
            "Final": "f",
        }
        
        #string comes in as unicode.
        string = str(string).strip()
        
        match_number = int(string[-1:])
        set_number = int(string[-3:-2])
        comp_level = comp_level_dict[string[:-4]]
        
        return {
            "match_number": match_number,
            "set_number": set_number,
            "comp_level": comp_level,
        }
