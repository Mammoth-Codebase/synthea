package org.mitre.synthea.world.geography;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import com.google.common.collect.Table;

import java.io.IOException;
import java.util.HashMap;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;
import org.mitre.synthea.helpers.Config;
import org.mitre.synthea.helpers.DefaultRandomNumberGenerator;

public class DemographicsTest {
  public static String demographicsFile;
  public static Demographics philly;
  public static DefaultRandomNumberGenerator random;

  /**
   * Set up the demographics to use for testing.
   */
  @BeforeClass
  @SuppressWarnings("rawtypes")
  public static void setUp() throws IOException {
    demographicsFile = Config.get("generate.demographics.default_file");
    Config.set("generate.demographics.default_file", "geography/test_demographics.csv");
    Table pa = Demographics.load("Pennsylvania");
    philly = (Demographics) pa.get("Pennsylvania", "27237");
    random = new DefaultRandomNumberGenerator(0);
  }

  @AfterClass
  public static void cleanUp() {
    Config.set("generate.demographics.default_file", demographicsFile);
  }

  @Test
  public void pickRace() {
    HashMap<String, Integer> raceMap = new HashMap<String, Integer>();
    for (int i = 0; i < 10000; i++) {
      String race = philly.pickRace(random);
      if (raceMap.containsKey(race)) {
        raceMap.put(race, raceMap.get(race) + 1);
      } else {
        raceMap.put(race, 1);
      }
    }
    assertTrue(raceMap.get("white") > 4300 && raceMap.get("white") < 4800);
    assertTrue(raceMap.get("black") > 4100 && raceMap.get("black") < 4700);
    assertTrue(raceMap.get("asian") > 500 && raceMap.get("asian") < 900);
  }

  @Test
  public void pickEthnicity() {
    int hispanic = 0;
    for (int i = 0; i < 10000; i++) {
      String ethnicity = philly.pickEthnicity(random);
      if (ethnicity.equals("hispanic")) {
        hispanic++;
      }
    }
    assertTrue(hispanic > 1000 && hispanic < 1600);
  }

  @Test
  public void languageFromRaceAndEthnicity() {
    HashMap<String, Integer> languageMap = new HashMap<String, Integer>();
    for (int i = 0; i < 10000; i++) {
      String language = philly.languageFromRaceAndEthnicity("white", "hispanic", random);
      if (languageMap.containsKey(language)) {
        languageMap.put(language, languageMap.get(language) + 1);
      } else {
        languageMap.put(language, 1);
      }
    }
    assertTrue(languageMap.get("english") > 4600 && languageMap.get("english") < 5000);
    assertTrue(languageMap.get("spanish") > 4900 && languageMap.get("spanish") < 5300);

    languageMap = new HashMap<String, Integer>();
    for (int i = 0; i < 10000; i++) {
      String language = philly.languageFromRaceAndEthnicity("white", "nonhispanic", random);
      if (languageMap.containsKey(language)) {
        languageMap.put(language, languageMap.get(language) + 1);
      } else {
        languageMap.put(language, 1);
      }
    }
    assertTrue(languageMap.get("english") > 9500);

    languageMap = new HashMap<String, Integer>();
    for (int i = 0; i < 10000; i++) {
      String language = philly.languageFromRaceAndEthnicity("asian", "nonhispanic", random);
      if (languageMap.containsKey(language)) {
        languageMap.put(language, languageMap.get(language) + 1);
      } else {
        languageMap.put(language, 1);
      }
    }
    assertTrue(languageMap.get("english") > 6400 && languageMap.get("english") < 7000);
    assertTrue(languageMap.get("chinese") > 900 && languageMap.get("chinese") < 1900);
  }

  @Test
  public void configuredLanguagesByRaceAndState() {
    try {
      Demographics.useLanguageDistributions(String.join("\n",
          "{",
          "  \"default\": {",
          "    \"black\": {\"zulu\": 0.5, \"xhosa\": 0.5},",
          "    \"white\": {\"afrikaans\": 1.0},",
          "    \"hispanic\": {\"spanish\": 1.0}",
          "  },",
          "  \"by_state\": {",
          "    \"Pennsylvania\": {\"black\": {\"sotho\": 1.0}}",
          "  }",
          "}"));
      // the test city is in Pennsylvania, so the state override applies to black
      for (int i = 0; i < 100; i++) {
        assertEquals("sotho", philly.languageFromRaceAndEthnicity("black", "nonhispanic", random));
        assertEquals("afrikaans",
            philly.languageFromRaceAndEthnicity("white", "nonhispanic", random));
        assertEquals("spanish", philly.languageFromRaceAndEthnicity("white", "hispanic", random));
      }
      // races without a configured distribution fall back to the built in behaviour
      assertEquals("english", philly.languageFromRaceAndEthnicity("native", "nonhispanic", random));
    } finally {
      Demographics.useLanguageDistributions(null);
    }
  }

  @Test
  public void builtInLanguagesWhenNothingConfigured() {
    Demographics.useLanguageDistributions(null);
    HashMap<String, Integer> languages = new HashMap<String, Integer>();
    for (int i = 0; i < 1000; i++) {
      String language = philly.languageFromRaceAndEthnicity("black", "nonhispanic", random);
      languages.merge(language, 1, Integer::sum);
    }
    assertTrue(languages.get("english") > 900);
  }

  @Test
  public void honorOtherRaceColumn() throws IOException {
    String previous = Config.get(Demographics.HONOR_OTHER_RACE_CONFIG);
    try {
      Config.set(Demographics.HONOR_OTHER_RACE_CONFIG, "true");
      Table<String, String, Demographics> pa = Demographics.load("Pennsylvania");
      Demographics city = pa.get("Pennsylvania", "27237");
      // test_demographics.csv lists OTHER as 0.001 for Philadelphia
      assertEquals(0.0, city.race.get("hawaiian"), 0.0);
      assertTrue(city.race.get("other") >= 0.001);
      double total = 0;
      for (double value : city.race.values()) {
        total += value;
      }
      assertEquals(1.0, total, 0.0001);
    } finally {
      if (previous == null) {
        Config.set(Demographics.HONOR_OTHER_RACE_CONFIG, "false");
      } else {
        Config.set(Demographics.HONOR_OTHER_RACE_CONFIG, previous);
      }
    }
  }
}