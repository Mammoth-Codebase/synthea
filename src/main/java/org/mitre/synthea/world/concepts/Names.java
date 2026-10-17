package org.mitre.synthea.world.concepts;

import java.util.List;

import org.mitre.synthea.helpers.Config;
import org.mitre.synthea.helpers.SimpleYML;
import org.mitre.synthea.helpers.Utilities;
import org.mitre.synthea.world.agents.Person;

/**
 * Provides utilities for generating and managing names.
 *
 * <p>Names are read from {@code names.yml}. The default file provides
 * {@code english} and {@code spanish} pools, each with {@code M}, {@code F}
 * and {@code family} lists. Any additional top level key is treated as another
 * language pool (for example {@code zulu} or {@code afrikaans}). A language pool
 * may optionally contain nested pools keyed by race (for example
 * {@code english.asian.M}) which are preferred, when present, for people of
 * that race. Unknown languages fall back to the {@code english} pool so that
 * existing configurations keep working unchanged.</p>
 */
public class Names {

  /** The pool used when a language has no entry in names.yml. */
  private static final String DEFAULT_LANGUAGE = "english";

  private static SimpleYML names = loadNames();

  private static SimpleYML loadNames() {
    String filename = "names.yml";
    try {
      String namesData = Utilities.readResource(filename);
      return new SimpleYML(namesData);
    } catch (Exception e) {
      System.err.println("ERROR: unable to load yml: " + filename);
      e.printStackTrace();
      throw new ExceptionInInitializerError(e);
    }
  }

  /**
   * Replace the loaded name pools with the pools defined in the given YAML content.
   * Intended for unit tests and for programmatic callers that want to supply their
   * own name lists without touching the classpath.
   * @param yamlContent YAML content in the same structure as names.yml
   */
  public static void loadNames(String yamlContent) {
    names = new SimpleYML(yamlContent);
  }

  /**
   * Indicates whether numbers should be appended to generated names.
   * These numbers are used to indicate the patients as not real people.
   */
  public static final boolean appendNumbersToNames =
      Config.getAsBoolean("generate.append_numbers_to_person_names", false);

  /**
   * Generate a first name appropriate for a given gender and language.
   * If `generate.append_numbers_to_person_names` == true,
   * then numbers will be appended automatically.
   * @param gender Gender of the name, "M" or "F"
   * @param language Origin language of the name, "english", "spanish"
   * @param person person to generate a name for.
   * @return First name.
   */
  public static String fakeFirstName(String gender, String language, Person person) {
    List<String> choices = namePool(language, gender, person);

    // pick a random item from the list
    String name = choices.get(person.randInt(choices.size()));

    if (appendNumbersToNames) {
      name = addHash(name);
    }

    return name;
  }

  /**
   * Generate a surname appropriate for a given language.
   * If `generate.append_numbers_to_person_names` == true,
   * then numbers will be appended automatically.
   * @param language Origin language of the name, "english", "spanish"
   * @param person person to generate a name for.
   * @return Surname or Family Name.
   */
  public static String fakeLastName(String language, Person person) {
    List<String> choices = namePool(language, "family", person);
    // pick a random item from the list
    String name = choices.get(person.randInt(choices.size()));

    if (appendNumbersToNames) {
      name = addHash(name);
    }

    return name;
  }

  /**
   * Find the most specific list of names available for the given language and key.
   * The lookup order is:
   * <ol>
   * <li>{@code language.race.key} when the person has a race attribute</li>
   * <li>{@code language.key}</li>
   * <li>{@code english.race.key}</li>
   * <li>{@code english.key}</li>
   * </ol>
   * @param language Origin language of the name, e.g. "english", "spanish", "zulu"
   * @param key One of "M", "F" or "family"
   * @param person person the name is for, used to look up the race attribute
   * @return a non-empty list of candidate names
   */
  static List<String> namePool(String language, String key, Person person) {
    String lang = (language == null || language.isEmpty())
        ? DEFAULT_LANGUAGE : language.toLowerCase();
    String race = null;
    if (person != null && person.attributes != null) {
      Object value = person.attributes.get(Person.RACE);
      if (value instanceof String && !((String) value).isEmpty()) {
        race = ((String) value).toLowerCase();
      }
    }

    List<String> pool = null;
    if (race != null) {
      pool = lookupList(lang + "." + race + "." + key);
    }
    if (pool == null) {
      pool = lookupList(lang + "." + key);
    }
    if (pool == null && race != null) {
      pool = lookupList(DEFAULT_LANGUAGE + "." + race + "." + key);
    }
    if (pool == null) {
      pool = lookupList(DEFAULT_LANGUAGE + "." + key);
    }
    if (pool == null) {
      throw new IllegalStateException("names.yml does not define a '" + DEFAULT_LANGUAGE + "."
          + key + "' name list.");
    }
    return pool;
  }

  /**
   * Safely look up a list of strings in the loaded names, returning null when any part
   * of the path is missing or is not a list.
   * @param path dot separated path, e.g. "english.M"
   * @return the list, or null if not present
   */
  @SuppressWarnings("unchecked")
  private static List<String> lookupList(String path) {
    try {
      Object value = names.get(path);
      if (value instanceof List && !((List<?>) value).isEmpty()) {
        return (List<String>) value;
      }
    } catch (NullPointerException | ClassCastException e) {
      // an intermediate path segment is missing or is not a map
    }
    return null;
  }

  /**
   * Generate a Street Address.
   * Street names are taken from the optional {@code street.name} list in names.yml,
   * falling back to english family names when that list is not defined.
   * @param includeLine2 Whether or not the address should have a second line,
   *     which can take the form of an apartment, unit, or suite number.
   * @param person person to generate an address for.
   * @return First name.
   */
  @SuppressWarnings("unchecked")
  public static String fakeAddress(boolean includeLine2, Person person) {
    int number = person.randInt(1000) + 100;
    List<String> n = lookupList("street.name");
    if (n == null) {
      // for now just use family names as the street name.
      n = (List<String>) names.get("english.family");
    }
    String streetName = n.get(person.randInt(n.size()));
    List<String> a = (List<String>)names.get("street.type");
    String streetType = a.get(person.randInt(a.size()));

    if (includeLine2) {
      int addtlNum = person.randInt(100);
      List<String> s = (List<String>)names.get("street.secondary");
      String addtlType = s.get(person.randInt(s.size()));
      return number + " " + streetName + " " + streetType + " " + addtlType + " " + addtlNum;
    } else {
      return number + " " + streetName + " " + streetType;
    }
  }

  /**
   * Adds a 1- to 3-digit hashcode to the end of the name.
   * @param name Person's name
   * @return The name with a hash appended, ex "John123" or "Smith22"
   */
  public static String addHash(String name) {
    // note that this value should be deterministic
    // It cannot be a random number. It needs to be a hash value or something deterministic.
    // We do not want John10 and John52 -- we want all the Johns to have the SAME numbers. e.g. All
    // people named John become John52
    // Why? Because we do not know how using systems will index names. Say a user of an system
    // loaded with Synthea data wants to find all the people named John Smith. This will be easier
    // if John Smith always resolves to John52 Smith32 and not [John52 Smith32, John10 Smith22, ...]
    return name + Integer.toString(Math.abs(name.hashCode() % 1000));
  }
}
