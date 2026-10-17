package org.mitre.synthea.world.concepts;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.List;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;
import org.mitre.synthea.helpers.Utilities;
import org.mitre.synthea.world.agents.Person;

public class NamesTest {

  private static final String TEST_NAMES = String.join("\n",
      "english:",
      "  M: [John]",
      "  F: [Mary]",
      "  family: [Smith]",
      "  asian: {M: [Rajesh], F: [Priya], family: [Naidoo]}",
      "spanish:",
      "  M: [Juan]",
      "  F: [Maria]",
      "  family: [Garcia]",
      "zulu:",
      "  M: [Sipho]",
      "  F: [Nomvula]",
      "  family: [Dlamini]",
      "street:",
      "  name: [Mandela]",
      "  type: [Street]",
      "  secondary: [Unit]",
      "");

  /**
   * Install a small set of name pools for the tests in this class.
   */
  @BeforeClass
  public static void setUp() {
    Names.loadNames(TEST_NAMES);
  }

  /**
   * Restore the real name pools so other tests are unaffected.
   */
  @AfterClass
  public static void tearDown() throws Exception {
    Names.loadNames(Utilities.readResource("names.yml"));
  }

  private static String strip(String name) {
    // numbers may be appended depending on configuration; strip them for comparison
    return name.replaceAll("[0-9]", "");
  }

  @Test
  public void languagePoolIsUsedWhenPresent() {
    Person person = new Person(1L);
    assertEquals("Sipho", strip(Names.fakeFirstName("M", "zulu", person)));
    assertEquals("Nomvula", strip(Names.fakeFirstName("F", "zulu", person)));
    assertEquals("Dlamini", strip(Names.fakeLastName("zulu", person)));
    assertEquals("Juan", strip(Names.fakeFirstName("M", "spanish", person)));
    assertEquals("Garcia", strip(Names.fakeLastName("Spanish", person)));
  }

  @Test
  public void unknownLanguageFallsBackToEnglish() {
    Person person = new Person(2L);
    assertEquals("John", strip(Names.fakeFirstName("M", "klingon", person)));
    assertEquals("Mary", strip(Names.fakeFirstName("F", null, person)));
    assertEquals("Smith", strip(Names.fakeLastName("klingon", person)));
  }

  @Test
  public void racePoolIsPreferredWhenPresent() {
    Person person = new Person(3L);
    person.attributes.put(Person.RACE, "asian");
    assertEquals("Rajesh", strip(Names.fakeFirstName("M", "english", person)));
    assertEquals("Priya", strip(Names.fakeFirstName("F", "english", person)));
    assertEquals("Naidoo", strip(Names.fakeLastName("english", person)));
    // a race without a sub pool uses the plain language pool
    person.attributes.put(Person.RACE, "black");
    assertEquals("John", strip(Names.fakeFirstName("M", "english", person)));
    // a language without a sub pool for the race uses that language's pool
    person.attributes.put(Person.RACE, "asian");
    assertEquals("Sipho", strip(Names.fakeFirstName("M", "zulu", person)));
  }

  @Test
  public void streetNamesComeFromStreetListWhenPresent() {
    Person person = new Person(4L);
    String address = Names.fakeAddress(false, person);
    assertTrue(address, address.endsWith(" Mandela Street"));
    String address2 = Names.fakeAddress(true, person);
    assertTrue(address2, address2.contains(" Mandela Street Unit "));
  }

  @Test
  public void namePoolLookupOrder() {
    Person person = new Person(5L);
    person.attributes.put(Person.RACE, "asian");
    List<String> expected = Arrays.asList("Naidoo");
    assertEquals(expected, Names.namePool("english", "family", person));
    assertEquals(Arrays.asList("Dlamini"), Names.namePool("zulu", "family", person));
    assertEquals(Arrays.asList("Smith"), Names.namePool("unknown", "family", null));
  }
}
